# E1 lane W1: the gates hold, the two cells are still missing, and the blocker is a binding

`inv_r1_w1_e1_gates`. Zero live dispatches. Machine-readable evidence:
`result.json`. Generator: `experiments/ad01/s09_e1_gates_probe.py`.

## Verdict

E1 is **not** unblocked, and this lane is the measurement saying so rather
than a recommendation. The three pre-dispatch gates in
`experiments/ad01/control_distinctness.py` were run first and are recorded
verbatim. The menu is open. The E1 control is **not** distinct from the
acquired arm, and the gate refuses it on the strategy leg. The two missing
representations are still missing: `typed-ast` and `action-graph` each
returned 156 refusals out of 156 instances, reproducing the committed
ceiling exactly.

The blocker is a missing SWE `World` binding, which the fork report
(`reports/STAGE-09-E1-FORK.md`) already identified and this lane confirms
from the executors rather than repeating. What is new here is that the
structural refusal is **cheap to reproduce** — it costs seconds, because
both cells are refused before an episode begins. So the E1 gap is a code
gap with a fast reproduction, not a measurement gap needing spend.

## The three gates, run first

Every gate's output is in `result.json` under `gate_report`. The refusals
are the finding and were not tuned away.

**`menu_answers_nothing` — passes.** The child menu is open: eight
callables are bound, `defaulting_strategy` is empty, and every wrapper
builds. Four callables carry a default for `priority`, which is the order
inside one strategy, not the strategy itself.

**`control_distinct` — refuses, on both AD01 column pairs.**
`evidence-ad01/c3-authored/use-w*-I.json` against
`evidence-ad01/c3-trajectories-merged/use-w*-I.json` (the files are at the
repository root, not under `reports/evidence/`):

```
refused: control is not distinct from the acquired arm:
  6 task(s) ran one strategy on both arms;
  6 task(s) ran one executed policy id on both arms;
  6 task(s) returned a byte-identical candidate on both arms
```

The **strategy** leg catches the six software tasks: the two arms differ
in `executed` id (`seed-sw-greedy` against `acquired-sw-58d90427`) but both
resolved to `greedy`, and only a smaller budget (16/13/14 queries against
4) made the candidates differ. The **executed-policy** and
**byte-identical-candidate** legs catch the six graph tasks, which ran the
same `incumbent` policy on both arms and returned identical candidates.

**`experience_varies` — refuses.** The AD01 acquired column's 72
observations grade a single verdict, `preserved`. This is the E2
all-`preserved` experience reproduced on the E1 records, and it is a
measured constant here, not an inherited claim.

## The control column, recounted

The fork report's section 5 finding is verified against the bytes, not
repeated from the report:

- `grep` for `ddmin` over `evidence-ad01/` returns **zero files**. The
  recorded control column of `6, 9, 8` appears in no committed record.
- `c3-authored` software records all carry `final_measure: 3` and
  `executed: seed-sw-greedy`. That is greedy, not ddmin.
- Both columns name `greedy` on all 24 software records. The 23-against-23
  tie was a wrapper around greedy against greedy.

## Per-representation state at today's tip

Re-run in this lane (the eight lineages the frozen executors refuse, which
execute no episodes, so this costs seconds):

| representation | n | repaired | unrepaired | refused | source |
|---|---|---|---|---|---|
| `typed-ast` | 156 | 0 | 0 | **156** | measured this run |
| `action-graph` | 156 | 0 | 0 | **156** | measured this run |
| `python-step` | 156 | 124 | 32 | 0 | carried from `inv_r1_e1_swe_ceiling` |

Both missing cells reproduce the recorded `156/156 refused` exactly. The
`python-step` row is **carried**, not re-measured: its four lineages
execute up to 307 subprocess turns per instance across 156 instances, so
a full re-run is hours. It is recounted from the committed file's own rows
and labelled `measured_this_run: false` in the result. The brief's
`python-step n=156 repaired=124 unrepaired=32 refused=0` is confirmed
against those rows.

The `typed-ast` refusal, verbatim from the run:

```
validator refused code.repair: action 'use' is not available in the Boolean world |
node set refuses view.source: probe.name: unknown view field 'source'
```

## The blocking seam

The `World` dataclass the graph executor takes is twelve constants, and the
three things SWE does not supply are measured from the executors in
`blocking_seam`:

1. **Action targets.** `World` names three (`probe_target`,
   `construct_target`, `stop_target`). SWE's vocabulary is five kinds
   (`observe`, `check`, `construct`, `use`, `stop`) across six targets. The
   three-target value does not fit the five-kind vocabulary without a shape
   change to `World` itself.
2. **Observation paths.** `World.field_type` falls back to the ordering
   regex `observed.(?P<x>[0-9]+).(left|right|earlier)`. A SWE observation is
   `{actual, expected, kind, test}` (read from a live session), so a SWE
   guard field resolves to `None` and the loader refuses it.
3. **The view.** The AST's `_VIEW_TYPES` has no field carrying the program,
   and its validator refuses `use`. The ordering `World` supplies
   `boolean_policy._shared_view`, so even a `World` value would hand the
   graph the Boolean view.

The `action-graph` cell's own recorded reason — "no swe World value
exists" — is confirmed. Building that value is a new binding, and the
experiment's author deliberately recorded the cells as missing rather than
quietly supplying it, because a binding is not the representation the cell
tests.

## What E1 can now claim

- The three gates hold, and the E1 control is not distinct from the
  acquired arm. The gate refuses it, and the refusal is the result.
- The two missing representations are still missing, at `156/156` each,
  reproduced in seconds from the executors. The ceiling is a code gap with
  a fast reproduction.
- The blocker is a missing SWE `World` binding plus the two executor
  extensions, not the eight-field view contract. The fork report's
  measurement and recommendation stand; this lane confirms the executor-
  side cause from source and does not contradict the view-fork analysis.

## What E1 still cannot claim

- A three-representation SWE matrix. Two cells are empty. A fresh run at
  today's tip would reproduce the refusals already recorded.
- Any claim about which representation is better on SWE. One cell wide is
  not a comparison.
- That the AD01 control column is attributable. It is not: no record of a
  ddmin control exists, and every committed record is greedy.
- A re-measured `python-step` number. It is carried from the ceiling
  matrix, not re-run here.

## Cost

Zero live dispatches. Zero gateway calls. Zero databases. The SWE world is
a local oracle and every lineage is an authored policy artifact, so the
matrix is recomputable in-process. The provider's absence of a zero is an
absence, not a measured zero: `live_dispatches.count` is `0` because
nothing was called, not because a provider reported nothing.

## Files

- `result.json` — machine-readable: all three gates, the control-column
  recount, the per-representation state, the blocking seam, `live_dispatches`.
- `experiments/ad01/s09_e1_gates_probe.py` — the generator. Reproduces every
  number above. Dispatches nothing.
- Cited: `reports/STAGE-09-E1-FORK.md`,
  `reports/evidence/inv_r1_e1_swe_ceiling/matrix.json`,
  `experiments/ad01/control_distinctness.py`,
  `evidence-ad01/c3-authored/use-w0-I.json`,
  `evidence-ad01/c3-trajectories-merged/use-w0-I.json`.
