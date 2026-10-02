# The acquired capability executed, once, under a real operation

Run against the repertoire committed by `inv_r1_m3_run7`, world 0, arm I, on
a disposable store provisioned the way the study provisions its campaigns.

```
ad01-w0-I-00-I-ad01-w0-within-sw-00 | acquired-sw-2074657c | red 0.70
ad01-w0-I-00-I-ad01-w0-within-sw-01 | acquired-sw-2074657c | red 0.769
```

The full record for the first:

| field | value |
|---|---|
| `executed` | `acquired-sw-2074657c` |
| `executed_source` | the `ENTRY` the model composed, verbatim |
| `verdict` | `preserved` |
| `initial_measure` | 10 |
| `final_measure` | 3 |
| `operation_ids` | `ad01-ad01-w0-I-00-use-ad01-w0-within-sw-00-acquired-sw-2074657c` |

## What this is and is not

It is a causal chain: model-authored bytes, a capability id, a real admitted
operation, an effect the checker re-derives, and a `preserved` verdict. The
previous 24 records could show none of that because all 24 refused.

It is **not** a comparison. One arm, one world, two tasks, no authored
control, and the selector that admitted the capability is the fallback that
picks the first eligible member rather than a policy the model acquired. So
this establishes that an acquired capability can execute and be scored, and
establishes nothing about whether it beats an authored baseline or whether the
model chose it.

## The remaining gap

The constructor offers two methods, `ddmin` and `greedy`, and `ddmin` is the
signature default. Every observed construction chose `ddmin`. Until the menu
is wide enough that the default is not the answer, an acquired method that
wins may be indistinguishable from one that was handed to the model.
