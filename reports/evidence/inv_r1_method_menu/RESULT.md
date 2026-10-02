# The method menu had the answer in its default

`reduce_software` and `reduce_graph` were offered as
`method="ddmin"|"greedy", max_queries=16` with **`ddmin` as the signature
default**. Every acquisition observed in this campaign chose `ddmin`, and the
authored control scored identically to the digit on every paired task. That is
what a defaulted argument produces: a caller that never chooses looks exactly
like one that chose correctly.

## What changed

`method` is now required, with no default, in both reducers. Every existing
caller already passed one, so removing it cost nothing. The two primitives
behind the wrappers, `ddmin_reduce` and `greedy_reduce`, plus the per-family
atom builders, are now offered to the constructor separately, so a choice can
be a strategy, a priority, a query budget, or a composition of them.

## What the model does now

Four live construction calls with the widened menu, same prompt shape:

| task | method named |
|---|---|
| `ad01-w1-dev-sw-01` | `greedy` |
| `ad01-w1-dev-sw-01` (repeat) | `ddmin` |
| `ad01-w2-dev-sw-00` | none, unparseable |
| `ad01-w0-dev-sw-00` | `ddmin` |

**The model now chooses, and the choice is not consistent.** Two `ddmin`, one
`greedy`, one nothing it could be parsed out of. Before the change every single
observation was `ddmin`.

## What this does and does not license

It licenses the comparison. With the default gone, an acquired capability that
matches the control is a real result, and one that beats it is a real result.
Neither was measurable before.

It does not license a claim that the model has learned which method suits which
task. Three calls is a sample, the distribution is not a preference, and one
call produced nothing usable. The honest summary is that the menu stopped
hiding the answer and the model started answering, inconsistently, which is the
minimum a comparison needs and not more.
