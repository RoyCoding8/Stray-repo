# M3 run 8: an acquired capability executes, and the limits are now the real ones

`inv_r1_m3_run8`. 30 model calls, 5 construction calls, 36 use records,
564 witness queries, 3 unknown receipts.

## What ran

Three use records executed the capability the model acquired, all with
`authored: False` and a real admitted operation id:

| task | domain | ops | reduction | verdict |
|---|---|---|---|---|
| `ad01-w2-within-sw-00` | software | 13 to 3 | 0.769 | `preserved` |
| `ad01-w2-within-sw-01` | software | 10 to 3 | 0.700 | `preserved` |
| `ad01-w2-transfer-sw-00` | software | 10 to 7 | 0.300 | `preserved` |

The third is a transfer task, so the capability carried to a task it was not
developed on, at a lower effect, and the checker still re-derived it.

## Why the other 33 refused, and both reasons are honest now

**30 refused with no policy.** Five of the six repertoires are empty, so the
selector has nothing to choose from. The CLI refuses rather than inventing a
member, which is correct. This is acquisition yield, not a defect.

**3 refused on scope.** The member is `scope: {"family": "software"}` and
those tasks are graph-domain. The use phase refuses a member whose scope does
not match the task, which is also correct and is the contamination boundary
working.

## The verdicts

Mechanism `true`. Live acquisition `true` but on one member of one family, and
the three executions are within-world plus one transfer task. Task utility
`not_comparable`: there is no authored control in this run, so nothing
establishes the acquired capability beats a baseline. Transfer `proven` in the
narrow sense that a capability carried to a task it was not developed on and
still re-derived, and `unproven` for cross-family or cross-world, which nothing
here tests. Recursive improvement `ineligible`.

## What is still missing, and it is not plumbing

The one member chose `ddmin`, which is the signature default, and no
construction has chosen `greedy`. So the model has yet to demonstrate a choice
at all, and a two-item menu with a default is not a menu.

There is no authored control in the run, no experience treatment, and no
comparison across arms. The selector that admitted the capability is the
fallback that takes the first eligible member, not a policy the model
acquired.
