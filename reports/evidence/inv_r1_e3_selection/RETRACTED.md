# The artifacts in this directory are retracted

Every result read off the JSON here is retracted. The files are kept unedited
because they are the record of what was claimed and when, and because deleting
them would destroy the evidence for the retraction itself. This notice sits with
them so a reader who opens the directory first cannot read them as live.

Three independent causes. None of the three is the one that mattered most, and
none of the three is stated in the artifacts.

## Cause 1 (N-80) — the ladder is cumulative prefix sums of one traversal

`crossover()` at `experiments/ad01/s09_e3_selection.py:133` constructs each
policy once with `policy = make_policy()` and only *then* enters
`for world in worlds`. Both policies are stateful, so one instance walks all
three worlds and all six budgets, and the control's totals are cumulative prefix
sums of a single traversal rather than three independent runs. This is what
`reports/STAGE-09-CONNECTED-STATUS.md:174` retracted. It was the only cause on
the record when this notice was written; the other two are independent of it and
neither is repaired by fixing it.

## Cause 2 (N-405) — the tight budget reports an advantage on a zero denominator

`e3-crossover.json` records `crossover.tight_budgets: [14]` — budget 14 is the
**only** tight budget — and at that budget:

| budget 14 | held_out | retained_behaviours |
|---|---|---|
| agenda | 0.1450565411349725 | 3 |
| control | **0.0** | **0** |

The control retained zero behaviours, so its `held_out_reduction_mean` is 0.0
because there was nothing to reduce, not because it reduced nothing well. The
artifact nonetheless records `agenda_ahead_on_held_out: true` there, and that
`true` is what `crossover.agenda_ahead_on_held_out_at: [14, 60]` is built on.

This is not post-hoc selection. `TIGHT` and `LOOSE` are module-level constants
with a stated rationale, fixed before the runs, and `tight`/`loose` partition a
pre-registered set. The zero denominator is a degenerate-evidence signature, and
it is independent of cause 1.

The same zero recurs at budget 8 (`control_held_out: 0.0`, `retained: 0`), but
budget 8 is not in `crossover.per_budget_budgets` (`[14, 20, 40, 60]`), so only
the budget-14 instance is load-bearing.

## Cause 3 (N-413) — the fix the roadmap credits to `52235a6` was never applied

`reports/STAGE-09-ROADMAP.md` attributes the stateful-policy-sharing repair to
`52235a6`. That commit fixed `sever_control()`, not `crossover()`. Verified:

- `52235a6` added `sever_control()`, which calls `make_policy()` **inside** its
  world and budget loops (`s09_e3_selection.py:294-299`).
- `crossover()`'s body is byte-identical across `02ce64b`, `52235a6`, `254f43e`
  and HEAD — one distinct body, sha256 `4e5a5c52cf9e5b1d`, 45 lines at each ref.
- Running `crossover()` at HEAD reproduces the committed `e3-crossover.json`
  byte for byte (sha256 `40dba4d6de15e16a`).

**The defect causes 1 and 2 exist to describe is still live in the code.** The
committed artifact is not stale; it is current. That is why the post-fix run had
to build a separate path rather than regenerate this one.

The post-fix ladder is at `reports/evidence/inv_r1_e3_ladder/` — its own
namespace, its own source (`experiments/ad01/e3_ladder.py`). With one policy per
cell, 42 of 48 measures move.

## What survives

- **`e3-admitted-operations.json` is not retracted.** It records 5 admitted
  decisions, 5 operations, 5 receipts at budget 40 on world 0 in the connected
  arm; the severed arm admitted 0 and wrote 0. This is the N-51 store-wiring
  result, it is a different claim from the ladder, and it stands.
- **The post-fix store verification stands.** The post-fix run verified 84
  operations and 84 receipts by SELECT, every one settled and every one carrying
  a decision, arriving by two paths (42 through `authority.admit_study_call`,
  42 through `selection.DecisionRecorder`). One caveat belongs with that number:
  the store's own contamination scanner sees only the first 42, and the gap
  between the two counts is itself a finding (ledger N-301). `84` is the
  durable-name-prefix count, not a `count(*)` over the table.
- **The treatment is active.** The post-fix ladder records 18 of 18 cells (3
  worlds × 6 budgets) diverging on the first choice.

## What is still not learned

Whether the agenda chooses *better* or only *more*. The post-fix data reverses
direction with the envelope: the agenda leads on held-out quality at budgets 14,
20 and 30, the control leads at 8, 40 and 60, and the control's margin grows
(0.359 at 40, 0.391 at 60, against the agenda's 0.145 and 0.206). A retained-behaviour
win is not a held-out win. The saturation explanation the old artifacts implied
was an artifact; the truth is not measured.

Recorded: `reviews/STAGE-09-FINDINGS.md` (N-80, N-413) and
`reviews/R3-VALIDITY-R4-REPRODUCTION.md` (N-405).
