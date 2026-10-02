# Stage 09 evidence findings: three committed artifacts that do not support their claims

Written before any regeneration, deliberately. The standing plan is to regenerate
these three artifacts, and the current files are the only surviving proof that
the defects existed. Regenerating first destroys that proof, so this write-up is
the precondition, not the documentation.

Nothing under `reports/evidence/` was modified, moved, deleted, renamed or
annotated in producing this document. No test suite or pytest run was executed.
The only file written is this one.

Every claim below carries its evidence in the same sentence, or is labelled a
guess. Measurements were taken by parsing the committed JSON at the three refs
named, and by reading the generator source at those refs.

---

## B1 — N-300 — the store witness's severed arm is unreachable

### 1. File paths and on-disk status

| Path | On disk at HEAD | On disk at `52235a6` |
|---|---|---|
| `reports/evidence/inv_r1_e3_selection/e3-store-witness.json` | **Yes.** 15,654 B, read in full this session | Yes, and byte-identical to HEAD (`git diff 52235a6 HEAD -- <file>` is empty) |
| `reports/evidence/inv_r1_e3_selection/e3-sever-control.json` | **Yes.** 41,192 B, read this session | Yes, byte-identical to HEAD. One commit only, `52235a6` |

Both files still exist and neither has been rewritten. `git log --oneline --
<file>` returns exactly one line each: `52235a6`.

The defect is duplicated across the two files. `e3-sever-control.json` embeds the
same two arms under `store_witness_connected` and `store_witness_severed`, with
the same severed-arm contradiction (`bindings` 0, `receipts` 4). Any repair must
touch both or the contradiction survives in one of them.

### 2. Exact path to the offending data

Primary, in `e3-store-witness.json`:

- **`severed.bindings`**, line **313**, value `[]`.
- **`severed.receipts`**, lines **321-402**, four populated receipt objects.
- Supporting contradiction, **`severed.operations_in_store`**, line **318**,
  value `0`.
- Supporting contradiction, **`severed.refused_decisions[*].operation_id`**,
  lines **408, 418, 428, 438**, each value `""`.

The connected arm is at lines 75-146 (`bindings`, 5 entries) and 154-255
(`receipts`, 5 entries), and is consistent.

Duplicate locations in `e3-sever-control.json` under
`store_witness_severed.bindings` and `store_witness_severed.receipts`.

### 3. Literal evidence

```
line 313:  "bindings": [],

line 318:  "operations_in_store": 0,

line 325:      "idempotency_key": "ad01-e3sever-cut-w0-s09sever-9c272c4b-op0-ad01-w0-dev-sw-00-seed-sw-ddmin-d2",
line 337:    "content_digest": "0ab865ac9f60f112c7a130f24a52e5f708f27566caa60a06c9063ab2eeba166e",
line 338:    "operation_id": "ad01-e3sever-cut-w0-s09sever-9c272c4b-op0-ad01-w0-dev-sw-00-seed-sw-ddmin-d2",
line 339:    "outcome": "success",
line 340:    "receipt_identity": "inline:ad01-e3sever-cut-w0-s09sever-9c272c4b-op0-ad01-w0-dev-sw-00-seed-sw-ddmin-d2"
```

Four such receipts, for `op0` through `op3`, tags `ad01-e3sever-cut-*`. All four
`refused_decisions` carry `"operation_id": ""` and
`"fallback_reason": "decision consumer disconnected: investigation portfolio
severed for the control condition"`.

The file's own disclaimer, `severed.witness_is_not_the_study` at line 480:
> "bindings are a counterfactual. operations_written_by_the_run is what the E3
> path itself persisted, and it is what bounds the claim that decisions reach
> real admitted operations."

### 4. How it was produced

One commit introduced the file: `52235a6`, "E3: the sever control ran, and it
exposed a worse gap than the one it fixed". The generator at that ref is
`experiments/ad01/s09_e3_selection.py`, `store_witness` at line **504**.

**The finding is not that the file was hand-edited. The finding is that the
generator at `52235a6` cannot produce it.** I checked the ref that wrote the
file, not HEAD, and the mechanism is different from the one the prior review
described.

At `52235a6`, `store_witness` binds every decision to a real operation itself
(lines 534-566), then returns (lines 584-616):

```
line 609:  "bindings": [] if sever else bindings,
line 611:  "receipts": read_back(dsn, [b["operation_id"] for b in bindings]),
```

`bindings` is the **only** source of the receipt id list. Under sever, the
list comprehension yields `[]`, so `read_back` receives an empty list. That is
the severed arm's contradiction, and it is unreachable at `52235a6` for the
same structural reason the prior review gave, though via a different expression
than HEAD's.

**The connected arm's `operations_written_by_the_run: 0` is reachable, and it
proves the run order.** At `52235a6`:

```
line 529:  before = _operation_count(dsn)
line 530:  run = run_policy(agenda_policy.agenda_policy(), world, budget, sever=sever)
line 532:  wrote = _operation_count(dsn) - before
line 534:  bindings, refused_operations = [], []      <- binding loop starts HERE
```

`wrote` is sampled at line 532, **before** the binding loop at line 534 that
calls `broker.ensure_operation`. So `operations_written_by_the_run: 0` at line
152 is what a correct run of this generator produces, because the count is
taken before the writes happen. It is not evidence of a hand edit.

This also explains `operations_in_store: 0` in the **connected** arm (line
151), which carries 5 settled receipts. Same cause, same ordering.

**What was supposed to have prevented it.** `tests/test_s09_e3_sever.py`, whose
docstring at line 390 asserts a refused decision is never given an operation id.
The test passed because the generator was self-consistent about the severed arm
returning `receipts: []`, and nobody checked the connected arm's `wrote: 0`
against its own 5 receipts. A test asserting `operations_written_by_the_run > 0`
whenever `receipts` is non-empty would have caught it at `52235a6`.

**This is a correction to `reviews/R2-EXECUTION-VISIBILITY.md:529`**, which left
open "Whether N-300 was a hand-edit or a bug in an older generator". I can now
close that question for the severed arm. The severed arm is unreachable at
`52235a6` **and** at HEAD (HEAD line 499 uses `read_back(dsn, operation_ids)`,
derived from `run.operations`, but `read_back` short-circuits at line 390 on an
empty list). The open question in the R2 review is a **guess** that the
generator was at fault; it is not resolved for the severed arm, and the R2
review's reproduction scripts (`/tmp/r2/probe_*.py`) were not read this session.

### 5. Why the claim is unsupported

The artifact is named a *store witness* and is cited as such in the N-51
completion cell. It asserts durable proof of work. For the severed arm it
asserts four settled, `success`-outcome operations against a store it also
records as holding zero operations, while every decision in the same arm is
recorded as refused with no operation id. A reader cannot distinguish this from
a genuine witness, and the internal disclaimer at line 480 does not cover the
contradiction.

The connected arm is a milder version of the same defect: it records
`operations_written_by_the_run: 0` beside 5 settled receipts, so the one field
the file's own disclaimer nominates as the bound on the claim is zero where the
claim is non-zero.

### 6. What the correct artifact should contain

For each arm, the following must hold and be checkable by `jq`:

- `receipts` is derived from the same id list that produces `bindings`, so a
  severed arm yields `bindings: []` **and** `receipts: []` together. Today only
  the bindings half is forced.
- `operations_in_store` counts operations this run admitted, not a global
  `count(*)` (N-301, already recorded). It must be `0` when `receipts` is empty
  and non-zero when `receipts` is non-empty, or the field must be renamed to
  what it actually measures.
- For a severed arm specifically, the expected and correct content is
  `bindings: []`, `receipts: []`, `admitted_decisions: []`,
  `operations_in_store: 0`, `operations_written_by_the_run: 0`,
  `refused_decisions` = 4 with `operation_id: ""`. Every one of those is
  already true in the committed file **except** the four receipts.
- The connected arm's `operations_written_by_the_run` must be `5`, matching its
  5 receipts, or the field must be dropped.

### 7. Is regeneration safe yet

**The finding is now fully documented. Nothing further needs reading before the
file can be touched.**

The severed arm's correct content is fully determined by the file's own
`refused_decisions` and `run_decisions` blocks, and I have written it out in
item 6. Regeneration is safe. One decision remains for the owning lane, and it
is a judgement, not a missing reading: the ledger's recommended action is "Delete
and regenerate; do not annotate", and I do not disagree. The regenerated file
should **not** overwrite the current one in place. Commit the new artifact under
a new name, leave `e3-store-witness.json` as the historical record, and point
the citation at the new file. Deleting the old file destroys the only evidence
that the defect existed.

Note that regenerating via the current `store_witness` will **not** fix the
connected arm's `wrote: 0`, because the ordering bug at lines 529-532 still
exists at HEAD. The regeneration lane must move the count, or accept `0` and
relabel the field.

---

## B2 — N-411 — the ceiling matrix was hand-edited and is not reproducible

### 1. File paths and on-disk status

| Path | On disk at HEAD | Note |
|---|---|---|
| `reports/evidence/inv_r1_e1_swe_ceiling/matrix.json` | **Yes.** 5,163,201 B | Byte-identical to `d183cbe`. Not touched by any commit after it |
| `reports/evidence/inv_r1_e1_swe_ceiling/RESULT.md` | **Yes.** 23,198 B | Modified in the same commit |

`git log --follow` on `matrix.json` returns exactly two commits: `d422c93`
(generated) and `d183cbe` (edited). **The file has not been regenerated.** The
evidence of the defect is intact.

### 2. Exact path to the offending data

Row selector: `rows[i]` where `i` is the **positional index** in the `rows`
array, not `task_id`. `task_id` is **not unique** — 468 rows carry only 39
distinct ids (429 duplicates), so any selector keyed on `task_id` will silently
match the wrong row. This is itself a hazard for a regeneration lane.

The affected rows are 60 specific positions. First three: **0, 6, 11**.

The offending field is the **last element of `rows[i].actions_emitted`**, plus
`rows[i].turns`.

Line numbers in the HEAD file, first affected row, from `git show d183cbe --
matrix.json`:

```
@@ -31707,10 +31707,6 @@
         {
           "kind": "use",
           "target": "code.repair"
-        },
-        {
-          "kind": "stop",
-          "target": "swe.task"
         }
       ],
       "fault_mechanism": "inverted_guard",
@@ -31725,7 +31721,7 @@
       "split": "dev",
       "structure": "counting",
       "task_id": "swe-dev-count-lead-sum-53207d",
-      "turns": 300
+      "turns": 299
     },
```

Line 31,707 of the pre-edit file, and the `turns` hunk at line 31,725.

### 3. Literal evidence

Terminal-action census, measured by parsing `rows[*].actions_emitted[-1]`:

| Ref | repaired + stop | repaired no stop | unrepaired + stop | unrepaired no stop | refused |
|---|---|---|---|---|---|
| `d422c93` (as generated) | **56** | 68 | **32** | 0 | 312 |
| `d183cbe^` (identical to generated) | **56** | 68 | **32** | 0 | 312 |
| `d183cbe` and HEAD | **0** | **124** | **28** | **4** | 312 |

First affected row, `rows[0]`, task `swe-dev-count-lead-sum-53207d`:

```
before: [{"kind": "construct", "target": "code.try"},
         {"kind": "use",       "target": "code.repair"},
         {"kind": "stop",      "target": "swe.task"}]        turns 300
after:  [{"kind": "construct", "target": "code.try"},
         {"kind": "use",       "target": "code.repair"}]      turns 299
```

Aggregate, measured: exactly **60** rows differ positionally between `d183cbe^`
and `d183cbe`. Of those, **56** are `repaired` and **4** are `unrepaired`. Every
one lost its terminal `{"kind": "stop", "target": "swe.task"}` and every one had
`turns` decremented by exactly 1. No other field changed on any row. `turns ==
len(actions_emitted)` holds **468/468** both before and after, so the edit is
internally consistent and would pass any invariant check that only compares
those two.

`git show d183cbe -- matrix.json` is 1,229 lines with 120 hunks; 60 removed lines
contain `swe.task`, and 0 added lines do.

### 4. How it was produced

Commit `d183cbe`, "N-65 follow-up, and the compacted SWE matrix", Sun Sep 27
18:44:08 2026. The commit message describes the change as a compaction:

> "The SWE lane's matrix.json is a compaction, not a regression: 5.1MB down by
> 300 lines, dropping 60 repetitive per-row turns/target/kind fields. Verified
> every collection is unchanged - 12 lineages, 16 missing cells, 468 rows, 24
> families, 5 derived bounds, both splits of probe_budget_reach, the 10-key path
> fork and search_span all identical"

The message is accurate about the collections and silent about the traces. It
does not say that 60 rows lost their terminal action. It calls the change
"dropping 60 repetitive per-row turns/target/kind fields"; the `target` and
`kind` of a terminal `stop` is not a duplicate of anything.

**This was not generated by a script.** The writer is
`experiments/ad01/s09_swe_experiment.py`, `result_payload` at line 1826 and
`_row_for_payload` at line 1758, writing through `write_evidence` at line 1860
to `os.path.join(out_dir, "matrix.json")`. `_row_for_payload` builds each row
from `row.as_dict()` and deletes five keys; it never removes a trace element. The
`actions_emitted` list is populated at line 1341 by iterating
`episode["trace"]` in `_row`, one entry per turn, with no filtering. Nothing in
the writer can drop a terminal action from 60 of 468 rows while leaving the other
408 alone. The edit was applied to the JSON after generation.

**The generator would produce the opposite of what is committed.** The `stop`
action is emitted by the STEP source string at
`s09_swe_experiment.py:914` (line 907 at `d183cbe^`), which is the terminal
`return` of the policy body:

```
return {"action": act("stop", "swe.task", {}), "state": state}
```

That line is unchanged between `d183cbe^` and HEAD, and a row that reaches the
end of its budget returns it. So regenerating today produces a file where a
substantial share of `repaired` rows **do** end in a `stop`, and the committed
file, where none do, cannot be the generator's output.

**What was supposed to have prevented it.** `tests/test_s09_matrix_size.py`
(added in `5e368eb`) reads the committed `matrix.json` and reconstructs every
claim from it. Its own docstring records the commit's measured `after` size as
**487,348 B, 21,343 lines**, but the committed file is **5,163,201 B**. The
artifact that the test treats as its reference is the pre-edit file, so the
interning fix in `5e368eb` was never applied to the committed artifact and the
test passes against a shape the repository does not contain. Nothing in the suite
compares the committed `matrix.json` against a fresh `result_payload` output, so
a post-generation edit to the JSON is invisible to it.

### 5. Why the claim is unsupported

`RESULT.md` at HEAD reasons about trace termination as a property of the run.
Line 17: "produced repairs: the search would have found a candidate and stopped."
Line 53: "search would have found a correct candidate and then stopped without"
Line 167: "turn 125 stop, with 149 probes unspent, best_passed = 2".

In the committed artifact, **no `repaired` row ends in a `stop` at all** (0 of
124), while 28 of 32 `unrepaired` rows do. "Does the trace end in a stop" is no
longer a derivable property of the committed evidence. It now correlates with
outcome, which is the opposite of what a reader would take from `RESULT.md`.
Re-running the generator will not reproduce the file, so the committed artifact
is not reproducible evidence.

### 6. What the correct artifact should contain

- Every one of the 468 rows as `result_payload` emits it, unmodified. In
  particular a `repaired` row that exhausted its budget must carry the terminal
  `{"kind": "stop", "target": "swe.task"}` the policy at line 914 returns, and
  `turns` must equal `len(actions_emitted)`.
- The 56/32 stop-vs-no-stop split of the `d422c93` file is the expected shape,
  because it is what the generator produced. I have not re-run the generator to
  confirm the split reproduces exactly; that is the regeneration lane's check.
- The `trace_sequences` interning from `5e368eb` may then be applied, and the
  result must still be byte-reproducible from `result_payload`.
- `tests/test_s09_matrix_size.py` must be repointed at whatever the regenerated
  file is, and must gain a check that the committed artifact equals a fresh
  `result_payload` output. That check is the thing whose absence allowed N-411.

### 7. Is regeneration safe yet

**The finding is now fully documented. Nothing further needs reading before the
file can be touched.**

The pre-edit blob is recoverable from git at `d422c93` and `d183cbe^`, both
byte-identical to each other (5,167,881 B), and it is a full generator output.
The defect is fully characterised above. Regeneration is safe.

Two costs a regeneration lane must accept, both measured here:

- The generator is `s09_swe_experiment.py`, and `test_s09_matrix_size.py:19`
  states a real 468-row matrix is "hours of wall clock and cannot be a test
  fixture". A full regeneration is expensive.
- `task_id` is not unique (39 distinct ids across 468 rows). Any verification
  keyed on `task_id` will match the wrong row. Use positional index, or a
  composite key.

---

## B5 — N-79 — two E3 artifacts share a digest and disagree

### 1. File paths and on-disk status

Both files exist on disk right now, and both are unchanged since they were
written.

| Path | On disk | Commit | Changed since |
|---|---|---|---|
| `reports/evidence/inv_r1_e3_selection/e3-store-witness.json` | **Yes** | `52235a6` | No. One commit in its whole history |
| `reports/evidence/inv_r1_e3_selection/e3-admitted-operations.json` | **Yes** | `a3b6cae` | No. One commit in its whole history |

**The two disagreeing files are still the evidence for this finding, and the
answer to the question the brief asked is yes.** A replacement was produced, and
it does not remove either of them. Both remain the only record of the
disagreement.

The replacement, `reports/evidence/inv_r1_e3_ladder/e3-postfix-ladder.json`,
exists on disk (165,045 B, commit `3c1e5c5`). It carries the **same**
`measure_digest`, so the collision the finding names is not confined to two
files.

### 2. Exact path to the offending data

In `e3-store-witness.json`:

- **`connected.operations_written_by_the_run`**, line **152**: `0`.
- **`connected.operations_in_store`**, line **151**: `0`.
- **`connected.measure_digest`**, line **150**:
  `"ce5a140aff83bccc55a916958fdbaf568cb7c576d5c6a66361510181c83cf7e8"`.
- **`severed.operations_written_by_the_run`**, line **319**: `0`.

In `e3-admitted-operations.json`:

- **`connected.operations_written_by_the_run`**: `5`.
- **`connected.operations_in_store`**: `5`.
- **`connected.receipts`**: 5 entries.
- **`connected.measure_digest`**: the same
  `"ce5a140aff83bccc55a916958fdbaf568cb7c576d5c6a66361510181c83cf7e8"`.

### 3. Literal evidence

The same measurement digest appears at ten sites across five committed files.
Measured by walking every JSON under `reports/evidence/`:

```
e3-store-witness.json     .connected.measure_digest            ce5a140aff83bccc...
e3-store-witness.json     .severed.measure_digest              ce5a140aff83bccc...
e3-admitted-operations.json .connected.measure_digest          ce5a140aff83bccc...
e3-admitted-operations.json .science_unchanged.measure_digest  ce5a140aff83bccc...
e3-admitted-operations.json .severed.measure_digest            ce5a140aff83bccc...
e3-sever-control.json     .control.measure_digest              ce5a140aff83bccc...
e3-sever-control.json     .store_witness_connected.measure_digest  ce5a140aff83bccc...
e3-sever-control.json     .store_witness_severed.measure_digest    ce5a140aff83bccc...
e3-crossover.json         .measure_digest                      ce5a140aff83bccc...
e3-postfix-ladder.json    .measure_digest                      ce5a140aff83bccc...
```

all ten equal to the full value
`ce5a140aff83bccc55a916958fdbaf568cb7c576d5c6a66361510181c83cf7e8`.

The disagreement, from the same dump:

```
e3-store-witness.json      connected   operations_written_by_the_run = 0
e3-admitted-operations.json connected   operations_written_by_the_run = 5
e3-sever-control.json      store_witness_connected wrote=0  bindings=5  receipts=5
e3-sever-control.json      store_witness_severed   wrote=0  bindings=0  receipts=4
```

So the collision is not two files. It is **five files sharing one digest while
reporting two different values of the same field**, and the "0" is recorded in
two of them.

### 4. How it was produced

`measure_digest` is not a digest of the artifact. It is
`selection.assert_measure_freeze()`, assigned at `s09_e3_selection.py:172` and
`:354` for the study and `:478` (HEAD) / `:588` (`52235a6`) for the witness. It
freezes the **measure set**, so it is identical across every artifact of the
study by construction. It is not evidence of a common measurement and cannot
distinguish two runs.

The two conflicting values come from the count ordering documented in B1, item
4: `_operation_count` before and after the run at `52235a6` lines 529-532.
`a3b6cae`, "N-51: E3's decisions now reach admitted operations with receipts",
is the later commit and is a descendant of `52235a6` (`git merge-base
--is-ancestor` confirms). It is a descendant, and it did not touch
`e3-store-witness.json`, so the older file was never marked superseded.

**What was supposed to have prevented it.** The digest was never meant to
discriminate between runs, so nothing in the design caught it. A reader is
invited to treat a shared digest as a shared measurement, and nothing in the
artifacts says otherwise. N-301, already recorded, is the underlying defect:
`_operation_count` is `SELECT count(*) FROM operations` over the whole
database, unscripted by run or campaign.

### 5. Why the claim is unsupported

Two committed artifacts in one namespace report opposite facts about whether E3's
decisions reached admitted operations, and the field designed to relate them
reports them as identical. A reader has no way to tell which is current, and the
one artifact that could have recorded the succession did not.

The claim is further weakened by B1. The "0" arm is the one carrying the
unreachable severed state, and its "0" is a count sampled before the writes it
measures. So the "0" is not a measurement at all.

### 6. What the correct artifact should contain

- One namespace, one current witness, marked with a `superseded_by` field or a
  sibling notice naming the file that replaced it.
- `measure_digest` must be accompanied by a **run digest** that varies between
  the two arms, so two files can never again be byte-equal on the field a reader
  would use to relate them.
- `operations_written_by_the_run` must be scoped to the run (N-301), and must be
  consistent with `receipts` in the same object, or the field must be renamed.
- The replacement should record what it replaced and why, in the artifact rather
  than only in a commit message.

### 7. Is regeneration safe yet, and is the replacement verifiable

**The finding is fully documented. Regeneration is safe. The replacement is
already produced and I verified it is script-backed.**

A correction to the brief. The brief attributes the regeneration note to
`5e368eb`. **`5e368eb` does not mention 84, operations, receipts or E3 at all.**
Its full message is about interning the 5 MB matrix, and it touches only
`experiments/ad01/s09_swe_experiment.py` and `tests/test_s09_matrix_size.py`.
`git show 5e368eb` contains no occurrence of the string `84`.

The regeneration the brief describes is **`3c1e5c5`**, "E3 post-fix ladder:
treatment INACTIVE, and the 227k-line matrix is a writer defect". Its message:

> "84 operations and 84 receipts, verified by SELECT rather than copied, which"
> "Cap sheet: 12 store cells × 7 decisions (the widest cell) = 84, derived from the ladder"

**Is the replacement verifiable from a committed script? Yes.**
`experiments/ad01/e3_ladder.py` defines `store_verdict` at line **453**, called
at line 825, and written into the artifact as `store_verdict` at line 886. The
committed `e3-postfix-ladder.json` `store_verdict` block records:

```
"operations_in_store": 84,
"receipts_in_store": 84,
"per_arm": {"agenda": {"carrying_a_decision": 42, "operations": 42,
                       "settled": 42, "success_receipts": 42},
            "control": {"carrying_a_decision": 42, "operations": 42,
                        "settled": 42, "success_receipts": 42}},
"per_path": {"admit_study_call": 42, "decision_recorder": 42},
"walked_operation_count": 42,
"walk_agrees_with_prefix": false,
"walk_missed": [ ... 4 operation ids ... ],
"counting_method": "SELECT over operations filtered by this study's own durable
                     name prefixes, never count(*) over the table, so a foreign
                     lane's row cannot be credited to this run (N-301)"
```

The replacement is script-backed, it names N-301 in its own counting method, and
it self-reports the discrepancy between the two counting paths
(`walk_agrees_with_prefix: false`, 42 walked against 84 counted). That is the
behaviour a store witness should have.

**One caveat to carry forward, and it is the same caveat the E3 `RETRACTED.md`
carries at line 77.** `84` is a durable-name-prefix count, not a `count(*)`
over the table, and the store's own contamination walk sees only 42. Both facts
are in the artifact. Anyone citing `84` must cite it with that caveat or they
will overstate it.

---

## Does `inv_r1_e3_selection/RETRACTED.md` cover N-300?

**No. It does not mention N-300 at all.** I read the file in full (4,890 B,
added in `4df45b2`). It names three causes and none is N-300:

- **Cause 1, N-80** — `crossover()` reuses one stateful policy across all worlds
  and budgets, so the control's totals are cumulative prefix sums. Stated at
  lines 11-20.
- **Cause 2, N-405** — the tight budget reports an advantage on a zero
  denominator, with a table of `held_out_reduction` and `retained_behaviours` at
  budget 14. Stated at lines 22-44.
- **Cause 3, N-413** — the fix the roadmap credits to `52235a6` was applied to
  `sever_control()`, not `crossover()`. Stated at lines 46-64.

The only N-number it names besides those three is **N-301**, at line 77, where
it records that "the store's own contamination scanner sees only the first 42".
**N-79 is not named anywhere in the file.** `grep -n 'N-300\|N-79\|N-301'`
returns the single N-301 line.

**What the file does cover about B1 and B5.** Under "What survives" at lines
68-80 it says:

> "**`e3-admitted-operations.json` is not retracted.** It records 5 admitted
> decisions, 5 operations, 5 receipts at budget 40 on world 0 in the connected
> arm; the severed arm admitted 0 and wrote 0."

**RETRACTED. This inference was wrong, and a lane established it by reading both
files rather than by reasoning about them.** The sentence is scoped to
`e3-admitted-operations.json`, and in *that* file the severed arm is genuinely
0 on every field -- `admitted_decisions`, `bindings`, `receipts`,
`operations_written_by_the_run` and `operations_in_store` are all 0, against 5
for the connected arm. Verified directly. The bullet is true of the file it
names and never names the witness.

The two files describe different runs of a repaired generator. The witness is
commit `52235a6`; the admitted-operations file is `a3b6cae`, a descendant, and
the generator changed between them (41 insertions, 151 deletions). The receipts
derivation is what moved: at `52235a6` the id list came from `bindings`, while at
HEAD it comes from `run.operations`
(`experiments/ad01/s09_e3_selection.py:501`) and `read_back` short-circuits on an
empty list at line 390, so the two now travel together. N-300 lives entirely in
`e3-store-witness.json` and `e3-sever-control.json`, which the bullet never
names. The v2 regeneration agrees with the bullet rather than against it.

**The real gap is scope, not truth.** `RETRACTED.md` never names N-300, so a
reader who trusts it may still trust the store witness. That is a missing
finding-id, not a false statement, and `ANNOTATION-B1-B5.md` in the same
directory already says the witness is superseded.

**What the file does not say.** It does not say the severed arm is structurally
impossible. It does not say the connected arm's `operations_written_by_the_run`
is sampled before the writes it measures. It does not say the witness and the
admitted-operations artifact disagree under a shared digest. A reader who
believes this notice will still believe the store witness is sound.

This is a defect **in the notice**, not in the artifacts. The notice should be
extended to carry N-300, and its "What survives" bullet corrected. I have not
edited it, per the brief.

---

## Regeneration status and safety

**Have any of the three been regenerated? No.**

- **B1 / N-300.** `e3-store-witness.json` has one commit, `52235a6`, and is
  byte-identical to HEAD. `e3-sever-control.json` likewise. Neither regenerated.
- **B2 / N-411.** `matrix.json` has two commits, `d422c93` and `d183cbe`, and is
  byte-identical to `d183cbe`. Not regenerated. The pre-edit generator output is
  recoverable from both `d422c93` and `d183cbe^`, which are byte-identical to
  each other.
- **B5 / N-79.** Both files exist unchanged. A replacement exists
  (`inv_r1_e3_ladder/`, commit `3c1e5c5`) and is script-backed, but it was
  produced alongside, not in place of, the pair.

**Is it safe to regenerate all three now? Yes, with one ordering constraint.**

All three findings are fully documented in this file. Nothing further needs
reading before any of the three can be touched.

The constraint is that regeneration must not overwrite in place. The current
files are the only surviving evidence that the defects existed, and this
document is the only record of what each defect actually was. Commit
regenerated artifacts under new names. Leave `e3-store-witness.json`,
`e3-sever-control.json` and `matrix.json` exactly as they are. Point the
citations at the new files. If a later reader needs to know what was wrong, this
document and the git history are what they get.

---

## Verification of the coordinator's correction

Asked to check the coordinator's B4 premise against the files, since the
coordinator reported being wrong twice today and asked for independent
verification.

**The correction is right, and the narrower claim is the accurate one.**

- `reports/evidence/inv_r1_e2_relevance/RETRACTED.md` names N-78 and N-400.
  Four occurrences. N-78 at line 11 as a section heading, `## Cause 1 (N-78) —
  both arms returned nothing at all`, with the mechanism spelled out: both arms
  record `"digest": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"`,
  which is `sha256("")`, and both record `"prompt_chars": 0`. N-400 at line 29 as
  `## Cause 2 (N-400) — the equal-length premise is false in the committed
  prompts`, with the 843/736/657/166/59 table. Both named again at lines 91-92.
- They are **not** in a subordinate "what is not claimed" section. They are the
  two top-level causes, the first of which the notice calls "fatal on its own".
  The subordinate section at lines 88-96 only records that they are
  "recorded, not repaired".
- **The attribution the coordinator suspected is not present.** The notice has a
  section headed "What the previous notice got right, and what it got wrong" at
  lines 74-86, which explicitly **rejects** the echo attribution: "That was
  wrong, and it named a different defect with a different fix", and cites
  `../inv_r1_e2_challenge/RESULT.md` as falsifying the echo mechanism. The
  coordinator's second concern is already handled.
- `reports/evidence/inv_r1_e2_transfer/RETRACTED.md` **exists** (832 B) and
  names neither N-78 nor N-400. So the open question the coordinator flagged is
  now closed: N-400 is not named in `_transfer` at all.

**The B3 claim, verified independently.** I recomputed rather than inherited.
`3011991aaae3` appears in seven files, five of which are the use-policy files R3
named. All four `inv_r1_e1_comparison/` use-policy files and
`inv_r1_m3b/repertoires/control-sw-use-policy.py` carry
`sha256 = 3011991aaae335d9d060a25d75096697243e17f33f986d64ee92738933246a06`,
per the listing at `reviews/R3-VALIDITY-R4-REPRODUCTION.md:432-436`. `db984e74726b`
appears in five files, and every one is prose: `reviews/R3-VALIDITY-R4-REPRODUCTION.md`,
`reviews/STAGE-09-FINDINGS.md`, `reports/STAGE-09-MILESTONE-AUDIT.md`,
`reports/STAGE-09-COMPLETION-MATRIX.md`, `reports/STAGE-09-MILESTONE-GAPS.md`.
Its only non-prose occurrence is the originating claim itself at
`reports/evidence/inv_r1_e1_comparison/RESULT.md:16`, which reads
`bytes hashed \`db984e74726b\``. **R3's withdrawal is correct, and it withdraws
exactly the byte-identity argument and nothing else.** E1's outcome table rests
on scores in the same `RESULT.md`, not on hashes, so it is untouched. Note for
B3's write-up: the count is five prose files, and R3's review is one of them,
so a claim that the digest "appears in five files" needs the R3 review excluded
to reach four.
