# C13 audit: `dispatch_state = 'sent'`

## Verdict

Not a defect. `sent` is a schema-permitted, read-only, **never-written** value. It has had no
producer since the first commit. The divergence is unreachable, costs nothing, and
`reset_dispatch`'s exclusion of `sent` is the deliberate fail-closed half of the pair.

## 1. Can a `sent` operation exist with no receipt?

**No.** There is no writer of `'sent'` anywhere, present or historical.

Complete list of `dispatch_state` writers in `src/`:

| file:line | value written |
|---|---|
| `store.py:1702` (`advance_dispatch`) | `'dispatching'` |
| `store.py:1977`, `2007` (`admit_receipt`, cost/settlement infeasible) | `'unresolved'` |
| `store.py:2024` (parameterized) | `state` from `store.py:2021`, which is only `'observed'` or `'unresolved'` |
| `store.py:2074` (`confirm_cancellation`, no proof) | `'unresolved'` |
| `store.py:2090` (`confirm_cancellation`, with never-sent proof) | `'cancelled'` |
| `store.py:2157` (`reset_dispatch`) | `'prepared'` |
| `store.py:2295` (`reconcile_operation`, never-sent proof) | `'reconciled'` |
| `store.py:2306` (parameterized) | `state` from `store.py:2304`, which is only `'reconciled'` or `'unresolved'` |

Both parameterized writers resolve to a closed two-value set in the line immediately above them
(`store.py:2021`, `store.py:2304`). The `INSERT` at `store.py:1670` hardcodes `'prepared'`. There
is no trigger, rule, or generated column on `operations` in any of the 18 migrations
(`grep -n "dispatch_state" migrations/` returns only the column default, the `CHECK`, and an index).

**History.** `git grep -E "dispatch_state[^a-zA-Z_]*=[^=]*'sent'"` across all 1627 revisions on all
refs returns nothing. A broader extraction of every literal ever assigned to the column across all
revisions yields `prepared` 5735, `dispatching` 4304, `cancelled` 647, `observed` 802,
`unresolved` 1865, `reconciled` 609, and `sent` 0. The `CHECK` at `migrations/0001_schema.sql:137`
admitted `sent` in the initial commit `aaa2948`, and `store.py:2382` shipped in that same commit.
The ghost has been in the schema and the readers from day one. It is an unimplemented state, not a
removed one.

**Empirical.** Across all 646 local databases, 5087 `operations` rows, zero rows have
`dispatch_state = 'sent'`. The observed distribution is `observed` 4631, `dispatching` 226,
`unresolved` 118, `prepared` 112.

So the "crash between marking sent and writing the receipt" shape cannot occur. The crash seam that
does exist is `_crash_after_send` (`broker.py:531`, `721`, `765`), which returns with the row still
at `'dispatching'` because `advance_dispatch` committed before the send. The window is real and is
correctly covered by `dispatching`.

## 2. What `sent` means versus `dispatching`

Nothing, because `sent` is never assigned. But the readers treat the two as synonyms.
`broker.py:310-311` maps both `"dispatching"` and `"sent"` to `awaiting-receipt` with identical
semantics, and `broker.py:3` states the only recovery state the system claims: "`dispatching`
means may-have-been-sent and is committed before any send."
`docs/design/PRACTICAL-SPECIFICATION.md:87` says the same and stops there. No document defines `sent`.

The exposure readers including `sent` are defensive, not meaningful: they are guarding against a
state the writer layer never produces. `reset_dispatch` excluding it is the fail-closed choice, and
it is **consistent with its sibling**. `reconcile_operation` at `store.py:2265` gates the
`reconciled` resolution on the same `("dispatching", "unresolved")` pair, for the same reason: a
`never_sent_proof` is only admissible when nothing was sent, and by definition a `sent` operation
had something sent. Both gates refuse a proof that would be false.

## 3. Reconcile path for a receiptless `sent` operation

None, and none is needed. `authority.py:26` puts `sent` in `STRANDED_DISPATCH_STATES`, and
`_stranded_exposure` at `authority.py:331-350` would count its reservation as lost rather than
pending, and `match` would go False. Money consequence: **zero**. Not one operation in 5087 local
rows is in that state. The asymmetry named in the task is real in the source but has no instance to
act on. It is a hypothetical about a state the code cannot produce.

## 4. Cheapest correct change

None is required for correctness. Two optional cleanups, neither load-bearing:

- `store.py:2133` raises `f"operation {op['id']} is {op['dispatch_state']}, not dispatching"` while
  accepting `('dispatching','unresolved')`. The message misreports the accepted set. A one-line
  message fix, cosmetic only.
- `tests/test_s09_n202_resend.py:174` asserts `state in ("sent", "observed")`. The real value is
  `observed`, so the `"sent"` arm is dead. It keeps the ghost state alive in the test surface and
  will mislead the next reader. Deleting `"sent"` from the tuple is safe.

## 5. Is R1's `_reclaimable` too narrow?

**No.** `_reclaimable` at `experiments/ad01/method_exec.py:344-360` is
`return state == "dispatching" and not receipted`. It is exactly right, for one reason that is
stronger than the one its docstring gives: it admits precisely the state that
`broker.redispatch_after_reset` can act on, and `redispatch_after_reset` bottoms out in
`store.reset_dispatch` (`broker.py:1268`), whose guard is the same `('dispatching','unresolved')`.
`_reclaimable` is narrower only in excluding `unresolved`, and `_durable_receipt` refuses
`unresolved` separately and earlier at `method_exec.py:370` and `method_exec.py:369`. The two
refusals compose; neither is a gap. Widening `_reclaimable` to `sent` would be unsound *and*
unreachable, and it would not help: `reset_dispatch` would refuse the resulting call.

## 6. What I could not determine

Only one residual, and it is not a code question. Someone with direct `psql` access could write
`'sent'` by hand; the `CHECK` admits it. No such row exists in any of the 646 local databases. What
would settle it completely is a check on the production cluster's `operations` table for
`dispatch_state = 'sent'`, which I cannot reach. If that returns zero, C13 closes as
unreachable-and-harmless, and the two cleanups in section 4 are the whole remaining work.
