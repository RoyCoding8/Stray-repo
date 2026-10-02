# The authored control, and what it shows about the acquired capability

The same use path, the same tasks, the same world. The only difference is
which repertoire the selector draws from: the capability the model acquired
versus the supplied `seed-sw-ddmin`, labeled `authored: True`.

| task | acquired | authored control | difference |
|---|---|---|---|
| `ad01-w2-within-sw-00` | 0.7692307692307693 | 0.7692307692307693 | **identical** |
| `ad01-w2-within-sw-01` | 0.700 | 0.700 | **identical** |

## What this means

The model acquired a capability, it executed, and the checker re-derived it.
That part is real and is what the previous run could not show.

But it performs **exactly** as the supplied authored reducer, to every digit,
on every task measured. And that is expected rather than surprising: the
acquired source is

```
def ENTRY(task, oracle, max_queries=16):
    reduction = reduce_software(task, oracle, method="ddmin", ...)
```

and `seed-sw-ddmin` is `reduce_software` with `method="ddmin"`. The model
reproduced the authored method by calling it, which is what the constructor
offered and what its signature defaults to. It is not an independent solution
and it is not an improvement. It is the authored baseline wearing an acquired
label.

## What this changes about the verdicts

Live acquisition `true`, in the narrow sense that model-authored bytes executed
and were scored. Task utility **`tie`**, not `not_comparable` and not a win.
Transfer `proven` in the narrow sense that the capability carried to a task it
was not developed on, and `unproven` for anything cross-family.

The honest reading is that the study now has a working end-to-end path from
model bytes to a scored, paired result, and the first such result is a tie
with the control. That is a real measurement. It is not evidence of learning.

## What would make the next run informative

A method menu where the default is not the answer, so a tie is not automatic.
And the prompt recorded with each response, so what the model was offered is
attested rather than inferred from what it returned.
