# E1 side result: an acquired `greedy` against the authored `ddmin` control

This is the use-phase scoring that preceded the representation matrix. It
answers a narrower question: when the model is offered a menu of
construction methods, does what it picks beat an authored control?

## The setup

Both repertoires were scored on the same three use tasks through the real
`experiments.ad01.cli use` path, on a disposable study with a subdivided
allocation, executing out of process.

- **acquired** — the live model wrote
  `reduce_software(task, oracle, method="greedy", max_queries=max_queries)`
  and returned it. Bytes hashed `cfadd1a52120`.
- **control** — the authored `seed-sw-ddmin`, bytes hashed `db984e74726b`.

## The result

| task | acquired `greedy` | authored `ddmin` |
|---|---|---|
| within-sw-00 | 5 (reduction 0.375) | 6 (0.250) |
| within-sw-01 | 10 (0.2308) | 9 (0.3077) |
| transfer-sw-00 | 8 (0.2727) | 8 (0.2727) |
| **total** | **23** | **23** |

Different bytes, different per-task outcomes, identical total. The
acquired policy wins one task, loses one, ties one.

This is a **tie**, and it is the second tie in this campaign. The first
was recorded before the method menu was widened, when the acquired source
called `reduce_software(..., method="ddmin")` and so was byte-identical in
effect to the control. Removing the default from the reducer's signature is
what made this measurement non-degenerate: before, every acquisition
chose `ddmin` because `ddmin` was the default, so the menu could not be
observed at all.

## What it does and does not show

It shows the model now chooses rather than inheriting a default, and that
its choice is not better than the authored control on these three tasks.
Three tasks is a sample. It is not an effect size, it is not a claim that
`greedy` is worse, and it says nothing about which method suits which
family — that is the question a larger run would ask, and the menu is now
in place to ask it.
