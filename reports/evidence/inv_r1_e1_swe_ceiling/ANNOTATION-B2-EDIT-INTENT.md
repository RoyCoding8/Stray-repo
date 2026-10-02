# B2 / N-411 — what the hand edit was doing, and what regenerating would change

Second pass on B2. `ANNOTATION-B2.md` in this directory has the measurement right
(60 rows, 56 `repaired` and 4 `unrepaired`, `turns` down by 1 each, nothing else
changed) and leaves two questions open. They are: **what the edit was trying to
achieve**, and **whether regenerating would change a number a report quotes**.
Both are answered here by measurement. The artifact is not touched.

The task row says "124 `repaired` rows lost their terminal `stop` and 28
`unrepaired` kept it." The measured edit is 60 rows, of which 56 are `repaired`
and 4 are `unrepaired`. The row conflates the terminal-action census with the
edit: 124 is the number of `repaired` rows *after* the edit, and 56 is the number
it *touched*.

## What the edit was trying to achieve

The rule is exact, and it fits all 468 rows with no residue:

> **Strip the trailing `stop` from every row whose trace contains a
> `use code.repair`. Leave a row that never applied a repair alone.**

- 60 rows contain a `use code.repair` and all 60 were edited.
- 28 rows end in a `stop` with no `use code.repair` anywhere in the trace, and
  all 28 were left alone.
- 312 rows have empty `actions_emitted` (all `refused`) and none were touched.

The edit was not a compaction, and it was not random damage. It was an attempt to
make one sentence true of the artifact. After it, in the committed file:

> a trace ends in a `stop` **if and only if** the arm never applied a repair.

That sentence is false of the run. It is a claim about the *instrument's* last
action, and the run's 56 `repaired` rows end in a `stop` precisely because a
successful repair **does not end the episode**. See the next section. The edit
made a true-looking regularity out of a generator artifact, and the regularity it
produced is the opposite of the mechanism.

The commit message (`d183cbe`, "dropping 60 repetitive per-row turns/target/kind
fields") describes it as a compaction. The message is accurate about every
collection it lists and silent about the traces. It is not a mis-description of a
compaction; there was no compaction in this file.

## The generator's own loop, which decides what a correct row looks like

`run_episode` at `s09_swe_world.py:531`, identical at `d422c93` and at HEAD:

```python
stopped = False
while not stopped and not is_terminal(session) and len(trace) < MAX_TURNS:
    ...
    stopped = effect["kind"] == policy_action.STOP
```

and `is_terminal(session)` is `session.is_repaired()`, which is set at
`s09_swe_world.py:381` and **only** by a successful `repair()` call. So the loop
has exactly three exits:

| exit | recorded as |
|---|---|
| the policy emitted a `stop` | trace ends with `{"kind": "stop", "target": "swe.task"}` |
| a repair succeeded | trace ends with `{"kind": "use", "target": "code.repair"}` |
| `len(trace) == MAX_TURNS` | trace ends with whatever it was doing |

**A successful repair is the last thing in the trace, always.** The loop checks
`is_terminal` at the top and exits without appending anything. So a `repaired`
row that ends in a `stop` means the repair landed on the second-to-last turn and
the policy then chose to stop anyway, which is legal, and which is what all 56
pre-edit `repaired`-ending-in-`stop` rows are. Measured: their `use` is at index
`turns - 2` in every one, and their turns span 296 to 307.

This gives a law that does not depend on the edit:

> **Terminal-action law.** Every non-empty trace ends in either
> `stop/swe.task` or `use/code.repair`. A trace ending in `use/code.repair` has
> `outcome: "repaired"`, because only a successful repair sets `is_repaired` and
> only a successful repair can be the trace's last action.

Measured against the two blobs:

| file | rows violating the law |
|---|---|
| `d422c93` and `d183cbe^` (as generated) | **0 of 468** |
| `d183cbe` and HEAD (hand-edited) | **4 of 468** |

The 4 are `swe-held_out-token-gaps-6bcae7` under `python-step-L0/L1/L2/L3`, each
`outcome: "unrepaired"` with a trace ending in `use/code.repair`. **The hand edit
did not merely lose information; it produced a state the generator cannot
produce at all.** Those 4 rows existed as `unrepaired` ending in `stop` before
the edit and the edit turned them into a contradiction.

## Would regenerating change a number a report quotes

**No.** Every aggregate in the file is byte-identical across the edit. Measured
by comparing all 14 top-level keys between `d183cbe^` and `d183cbe`:

| collection | changed by the edit |
|---|---|
| `rows` | **yes, 60 rows, 2 fields** |
| `per_family` | no |
| `paired` (1,872 entries) | no |
| `derived_bounds` | no |
| `search_span` | no |
| `support` | no |
| `lineages`, `missing_cells`, `probe_budget_reach`, `path_fork` | no |
| `representations`, `instrument`, `template_version`, `world_module`, `notes` | no |

On the 60 edited rows the only fields that differ are `actions_emitted` and
`turns`. Nothing else on any row.

The outcome census is unchanged, which is the number the reports actually use:

| outcome | `d183cbe^` | `d183cbe` and HEAD |
|---|---|---|
| `repaired` | 124 | 124 |
| `unrepaired` | 32 | 32 |
| `refused` | 312 | 312 |

`per_family` is identical, so **16 of 24 families fully repaired** stands, and so
does every per-family rate. Total actions across 468 rows move from 47,320 to
47,260, and no report quotes that.

`RESULT.md` in this directory quotes no per-row `turns` value. Its numbers are
`468`, `24 families`, `16 of 24`, `124`, `156`, `60 dry-runs`, `302`, `303`,
`307`, `269`, and a worked example at `turn 112` / `turn 125`. Every one of those
is invariant under the edit. The worked example is on task
`swe-held_out-count-tail-sum-1fdc31`, which the edit did not touch (verified
positionally: it is an untouched row in all four lineages).

Searched `reports/` for a claim that depends on trace termination, by three
patterns: a count of rows or traces paired with `stop`, a claim that `unrepaired`
rows end in `stop`, and a claim that every episode ends in `stop`. The only hits
are `ANNOTATION-B2.md` and `reports/STAGE-09-EVIDENCE-FINDINGS.md`, and both
already state the before and after censuses side by side. **Regenerating would
change no number any report quotes, and would make two documents newly correct
rather than newly wrong.**

## Is the hand edit still needed

**No, and it cannot be.** The 56/32 split of `d422c93` is what the generator
produced. The 4 contradictory rows are the only thing the edit added, and they
are the reason to remove it.

Restoring is not a re-run. `d422c93` and `d183cbe^` are byte-identical
(5,167,881 B, sha256 `5928d4e1f66119ae…`) and are a full generator output, so the
pre-edit file is a `git cat-file`. `ANNOTATION-B2.md` records the two reasons a
re-run at HEAD is the wrong route, and both hold: `5e368eb` changed the writer's
row shape, so a regeneration produces a structurally different file rather than a
corrected one, and a real 468-row matrix is hours of wall clock.

## What the guard should assert

`test_a_real_matrix_ends_every_episode_where_the_loop_allows` exists at
`2bacba3` and is red against the committed file on purpose. It is red for the
right reason and it is the check whose absence allowed N-411. It should also
assert the stronger half of the law, which is the one that actually discriminates:

> a row whose trace ends in `use/code.repair` has `outcome: "repaired"`.

That direction is what the edit broke, it is decidable from the artifact alone,
and no invariant comparing `turns` to `len(actions_emitted)` can see it. Both
invariants are invariant under a 60-row trace edit, which is why both survived.
