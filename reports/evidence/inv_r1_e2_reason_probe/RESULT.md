# E2: rendering `reason` does not unblock the gate

`cfa8ab3` stopped E2 at its gate and named two changes that would make a
dispatch worth spending: a panel of tasks the authored reducers fail, and a
prompt that renders `reason` beside `verdict` (or a scored observable the
budget actually moves). It called the second one smaller and more diagnostic,
and directed work to start there.

Measured, it does not move the gate, and the reason is that the gate and the
prompt read different fields.

## The gate reads `verdict`. The proposed change renders `reason`.

`experience_varies` counts distinct values of a record's `verdict`. Handing
the gate records that also carry a `reason` changes nothing it reads:

| Records handed to the gate | Distinct verdicts | Gate |
|---|---|---|
| verdict only, as the arms build them | 1 (`preserved`) | **refused** |
| verdict plus reason | 1 (`preserved`) | **refused** |

The refusal is the same sentence either way: *3 observations, 1 distinct
verdict(s) `['preserved']`, minimum 2*.

## The signal the change would add is real

The reason is not a constant the way the verdict is. Across the whole frozen
world, over 216 task-budget pairs:

- verdicts: `preserved` on all 216
- reasons: `ok-incumbent` 96, `ok-preserved` 120

On the freeze's own three source tasks the reason moves with budget exactly as
`cfa8ab3` described:

| Budget | Reason | Verdict |
|---|---|---|
| 1 | `ok-incumbent` | `preserved` |
| 8 | `ok-preserved` | `preserved` |
| 64 | `ok-preserved` | `preserved` |

So rendering `reason` would give a policy a varying signal that the verdict
collapses. That is worth having, and it is not what the gate is asking for. At
the budget the freeze pins (8) all three tasks earn `ok-preserved`, so even
the reason-bearing arm is a constant at the budget the run would use.

## What this reorders

A panel that varies, and a gate that reads the field which varies, are both
needed before a dispatch is worth spending. Rendering `reason` supplies the
second without the first. The panel change `cfa8ab3` named first is the one
that can produce a panel carrying more than one verdict, because the only way
these reducers earn `not_preserved` or `invalid` is to fail, and they solve
every task in the frozen world.

Nothing was dispatched. `dispatches: 0`, no database, no gateway call, and
the API key was never read.

Regenerate with:

    .venv/bin/python -m experiments.ad01.e2_reason_probe
