# Superseded: `matrix.json` was hand-edited and is not reproducible. B2 / N-411

`matrix.json` is superseded and is **kept unedited**. It is the only surviving
proof that the defect existed, and the write-up at
`reports/STAGE-09-EVIDENCE-FINDINGS.md` is a precondition for touching it, not
a replacement for it.

- **Write-up:** `reports/STAGE-09-EVIDENCE-FINDINGS.md`, item B2.
- **Replacement:** none. See "Why nothing was regenerated" below. This is the
  documented outcome, not a gap.

## The defect

A hand edit in `d183cbe` ("N-65 follow-up, and the compacted SWE matrix",
Sun Sep 27 18:44:08 2026) stripped the terminal
`{"kind": "stop", "target": "swe.task"}` from **60 rows** and decremented
`turns` by 1 on each.

| | `d183cbe^` (as generated) | HEAD (after the edit) |
|---|---|---|
| `repaired` ending in `stop` | **56** | **0** |
| `repaired` not ending in `stop` | 68 | 124 |
| `unrepaired` ending in `stop` | **32** | 28 |
| `unrepaired` not ending in `stop` | 0 | **4** |
| total actions across 468 rows | 47,320 | 47,260 |
| rows where `turns == len(actions_emitted)` | 468 / 468 | 468 / 468 |

Exactly 60 rows differ positionally between `d183cbe^` and `d183cbe`: 56
`repaired`, 4 `unrepaired`. No other field changed on any row.

`turns == len(actions_emitted)` holds on **both** sides, so the edit is
internally consistent and would pass any invariant that compares only those
two fields. That is why it survived.

## The selector is positional, and `task_id` is not unique

468 rows carry only **39** distinct `task_id` values. Any verification keyed on
`task_id` silently matches the wrong row. Select by **positional index** in
`rows`, or by a composite key of lineage plus lineage digest plus task id.
Every count in the table above was taken positionally.

## What it breaks

`RESULT.md` reasons about trace termination as a property of the run
("produced repairs: the search would have found a candidate and stopped",
line 17; "turn 125 stop, with 149 probes unspent", line 167). In the committed
artifact **no `repaired` row ends in a `stop` at all**, 0 of 124, while 28 of
32 `unrepaired` rows do. "Does the trace end in a stop" is no longer derivable
from the evidence. It now correlates with outcome, which is the opposite of
what a reader would take from the prose.

## Why nothing was regenerated

Two measured reasons. Either alone is sufficient.

**1. The pre-edit blob is recoverable and complete, so there is nothing to
regenerate.** `d183cbe^` and `d422c93` are byte-identical
(sha256 `5928d4e1f66119ae…`, 5,167,881 B) and the blob is a full generator
output. Restoring it is a `git cat-file`, not a re-run. The honest correction
to the write-up is that the *file* was never lost. What was lost is the
knowledge that it had been edited, and that is what this notice and the
write-up carry.

**2. A re-run at HEAD cannot reproduce the pre-edit shape, because the writer
changed after the artifact was written.** `5e368eb` ("N-410: the 5 MB matrix
was 90% repeated trace; the writer now interns it", Sep 28 06:46) rewrote
`result_payload` and `_row_for_payload`. The committed `matrix.json` has
`actions_emitted` **inline per row**, no top-level `trace_sequences`, no
`lineage_index`, and no per-row `trace_sequence` or `lineage_id` reference. The
current `_row_for_payload` at `s09_swe_experiment.py:1758` deletes exactly
those inline keys and writes a reference instead, and `result_payload` at line
1822 emits `trace_sequences` and `lineage_index`.

So a regeneration run today produces a **structurally different file** from
both the committed one and the pre-edit one. Committing it under a new name
would put a third artifact into a namespace that already has two shapes, and
the reader would have three incompatible row formats to choose between. It
would not be a correction. It would be a third thing.

A full run is also not cheap. A real episode is a bounded out-of-process
child per turn with a ten second budget, and `tests/test_s09_matrix_size.py:17`
records that a real 468-row matrix is hours of wall clock. In this lane a
single lineage over the dev split alone had not finished after 9 minutes of
wall clock, and this lane stopped it rather than hold the branch for a run
whose outcome cannot change the decision above. The structural reason above
is the one that decides it; the cost is only a reason to prefer the
`git cat-file` route, not the reason the regeneration is wrong.

## What a correct artifact would contain

- All 468 rows exactly as the generator emitted them, with the 56/32
  stop-terminated split of `d422c93` restored, since that is what the generator
  produced.
- The `5e368eb` interning applied, so the file is no longer a function of trace
  length, and still byte-reproducible from `result_payload`.
- A test asserting the committed artifact equals a fresh `result_payload`
  output. That check's absence is what allowed N-411, and `5e368eb` did not
  add it.

## Not fixed here

The committed file stays as it is. It is superseded by this notice. I
corrected one claim from the write-up while checking it. A **second**
correction follows at `2bacba3`. The first said `tests/test_s09_matrix_size.py`
does **not** read the committed `matrix.json`. It does, at `:322`.

What is true is narrower, and is what actually mattered: that test's three
assertions are **invariant under this edit**, so it read the file and saw
nothing wrong with it. Announcing that a reader does not read a file that does
read it makes a real gap look unfixable when it was simply unguarded.

The check whose absence allowed N-411 is now present, added at `2bacba3`.
`test_a_real_matrix_ends_every_episode_where_the_loop_allows` reads the committed
artifact and asserts the law taken from the generator's own loop: `world.run_episode`
exits three ways, leaving an explicit stop, a walk of exactly `MAX_TURNS`, or a
successful `use code.repair` satisfying `is_terminal`. A trace ending in a repair
whose row is `unrepaired` is a contradiction, and the cap is read from the
artifact's own `derived_bounds` rather than pinned.

That test is **red against the committed file, deliberately.** The defect is
recorded, not repaired, and the test says so. What the write-up got
right is the consequence: nothing anywhere compares the committed artifact
against a fresh `result_payload` output, and that missing check is what let
N-411 stand. Its own docstring records a measured 487,348 B / 21,343 lines,
against a committed file of 5,163,201 B, so the interning fix it describes was
never applied to the committed artifact. Repointing or extending that test is
out of this lane's scope: it lives under `tests/`, which a concurrent full
suite is measuring.
