# C22: what the expenditure digest is for, and what a correction is

The decision: `src/settlement/trials.py:253` builds its idempotency identity
from the protocol and the operation only, leaving `category`, `amount` and
`note` out of it. Both consequences are real, one is a bug, and the other
turned out to be the design working.

It was referred to me as a question for a person. It was not. It is
settled below by measurement, and the answer is a change I have made.

## Every writer of `expenditure_ledger`

The table is defined at `migrations/0003_s3_learning.sql:152`. In the
production tree there is exactly one writer:

| Writer | Location | Path |
| --- | --- | --- |
| `trials.record_expenditure` | `src/settlement/trials.py:202` (INSERT at 265) | Through `store.transact` |

It is reached from one place in production code:

- `experiment._settle_costs` at `src/settlement/experiment.py:563`, which
  loops over `set(protocol_ids)` and calls `record_expenditure` once per
  protocol.

`_settle_costs` has many callers (`experiment.py` lines 660, 670, 696, 735,
752, 1041, 1061, 1073, 1203, 1237, 1242, 1336, 1342, and `development.py`
lines 392, 402, 591, 638, 756, 792, 898, 905, 921), but every one of them
is a distinct operation, so the loop-over-protocols behaviour is the one
that makes the narrow digest load-bearing.

Non-production writers, which bypass the digest entirely and are not
affected by this change:

- `tests/test_r01_deadline_ui.py:209` inserts rows directly to build UI
  fixtures.
- `reports/evidence/eng-close2/run_smoke.py:155` only reads.
- `tests/test_invl02_accounting.py:298` matches the INSERT string inside a
  fake `transact`.

There is no second path in `src/settlement/gateway_http.py`; the other live
lane does not touch the ledger, so there is no conflict to report.

The last thing worth noting about writers: nothing anywhere updates or
deletes a ledger row. A grep for `UPDATE expenditure_ledger` and
`DELETE FROM expenditure_ledger` across the whole tree returns nothing.
The table is append-only in fact, not only in intent.

## What the idempotency is really doing

Both, and the split is not the one the code suggests.

`store.transact` (`src/settlement/store.py:248`) digests the whole command
payload at line 250 and looks the request up in `command_journal` at lines
276-290:

```python
found = cur.fetchone()
if found is not None:
    conn.commit()
    if found["payload_digest"] != digest:
        raise ConflictPayload(...)
    result = _stored(found)
    if result.code == ResultCode.APPLIED:
        result.code = ResultCode.ALREADY_APPLIED
    return result
```

So there are two digests, and they do different jobs:

- **The journal digest** (`payload_digest(cmd.payload)`, store.py:250) is
  what actually prevents duplicate application. It is a conflict detector:
  same `request_id` plus a different payload is refused, and same
  `request_id` plus the same payload returns the stored result without
  re-running the handler.
- **The identity digest** (`payload_digest({protocol_id, operation_id})`,
  trials.py:253) exists only to *derive the `request_id`*. It is not a
  second layer of protection. Nothing compares it to a stored column,
  because there is no column to compare it to.

The old `Command.payload` (a literal dict, now the `charge` variable at
trials.py:279) already carried `category`, `amount` and `note`, and the
journal digest already covered them. So the
narrow identity was producing a `request_id` that stayed *stable* while the
journal digest *moved* — and `store.py:285` then refused. The conflict was
manufactured by the identity function, not detected in the data.

**The evidence that settled it** is what the amount actually is. It is
measured, not stated:

- `experiment._op_accounting` (`experiment.py:495`) derives `settled` from
  the operation's receipts, reservation state, dispatch state and billing
  state.
- For an operation left `unresolved`, it returns `{"settled": 0,
  "unresolved": reserved}` (`experiment.py:527-529`).
- `broker.reconcile` (`broker.py:1040`, called from the recovery loops at
  `broker.py:1203, 1231, 1254, 1398`) settles the same operation later, and
  the same function then returns a real amount.

I confirmed the settled path is the live one: a dispatched sandbox
operation reports `settled: 111, outcome: success, dispatch_state:
observed`, from a throwaway probe I ran and deleted.

So the second call is not a caller mistake. It is the *same caller, the same
call site, the same operation*, re-measured after the operation finished
settling. The first reading was provisional. The old digest refused exactly
the case the field exists to record, which is why this looked like a policy
question and was actually a bug.

## The choice, and where the caller's view was wrong

I chose **(a), widened to the whole charge**. Not (b), and the reason is
that option (b) was asked for on a premise the schema does not support.

The stated worry: "a correction that overwrites or merely sits beside the
original is exactly what an audit has to reason about, and a money path
should not make that easy." I agree with the first half. I do not agree
that the schema gives the alternative any purchase:

- The ledger has **no supersession concept**. One `supersedes` column
  exists in the whole schema, on `trial_protocols` (`migrations/0003_s3_learning.sql:85`),
  where it means "this protocol version amends that one". No migration
  carries one for the ledger.
- The ledger is **append-only by construction** — zero UPDATE/DELETE
  sites, as above.
- `amount` is `CHECK (amount >= 0)` (line 158). A charge cannot be
  retracted, and a reversing row is not expressible as a distinct state.

So (b) would mean inventing a reversal concept for a table that cannot
represent one. And the version of (b) that *is* expressible — a new
operation carrying a correcting charge — is what a widened digest already
produces, except that the operation is the honest one, the one that really
happened, rather than a synthetic correction operation that never happened.
A synthetic operation is a worse lie than two rows that both point at real
receipts.

There is one cost I could not argue away, and I want to be explicit about
it rather than let it read as settled. Under (a) a correction **double
counts**: every reader of this table is `SUM(amount) GROUP BY category` —
`trials.development_expenditure` (trials.py:291), `api.py:201`, `api.py:255` —
so a corrected protocol reports both the provisional and the real charge.
Under (b) with a reversing row, `SUM` would net them to zero. If the
priority were "the reported total must equal the money actually spent",
(b) would win, and (b) is what I would build.

But the ledger is unsigned. A reversal row is not a negation; it is another
positive amount that happens to be the same magnitude, and the netting is an
accident of arithmetic, never a declaration. Nothing in the table says
"this row undoes that row", so an auditor reading the rows one at a time —
which is how an audit actually proceeds — learns nothing from a `-41`
encoded as a second `+41`. The double count is visible and the phantom
cancellation is not. And the way out of the double count is not to
reconstruct intent in a sign convention; it is for the caller to re-charge
and read the second row as superseding the first, which is exactly what the
docstring now says.

**Where the caller was wrong:** the premise that (b) is available. It is a
correct instinct applied to a table that has already chosen the other
answer, by having no way to express the alternative. The instinct was sound
and the schema is the evidence; I followed the schema.

**Where the caller was right, and I want to be even-handed:** the worry that
this is a money path and should not be made easy is not defeated by the
absence of a supersession column. It is unaddressed by my change. Under
(a), correcting a charge is *easier* than it was. Nothing in the code stops a
careless caller from double-booking a protocol's whole development cost.

I did not fix that, and I want to be honest that I am leaving it, rather
than presenting a settled question where there is a real one underneath. The
two options are a nullable `supersedes` column on the ledger with readers
that follow it, or an explicit `corrects` argument on `record_expenditure`
that refuses an uncorrected row, and both are schema changes to a table
under `reports/evidence/`. That is a larger decision than this lane owns, and
it should be made deliberately rather than as a side effect of fixing a
digest. What I have done is make the model explicit in code and docstring,
so the next reader knows which ledger they are reasoning about — and
`test_the_ledger_has_no_way_to_retract_a_charge` now pins the double-count
so it cannot be discovered later by someone assuming otherwise.

## Replay safety: proved before and after

The instruction was to write this test first, so it is the first commit
(`d9ecb99`), written before any decision.

`test_replaying_one_charge_does_not_double_apply` charges one operation
three times with identical arguments and asserts one row.

**It held before the change** — measured, not assumed. The first run at
commit `d9ecb99` against the old code: this test passed, and only the
changed-amount case failed. Replay safety was never at risk from the
narrow digest, because the journal was already doing the work. The narrow
digest was breaking corrections, not duplicates.

**It holds now**, and the interesting half is that widening the identity did
not weaken it. A correction is itself idempotent against itself:
`test_recording_the_corrected_charge_twice_still_books_it_once` books the
corrected charge twice and asserts two rows, not three.

Both are falsifiable in both directions. Giving each call a unique
`request_id` — simulating a lost idempotency key — makes the identical
replay double-apply, and both replay tests fail:

```
FAILED test_replaying_one_charge_does_not_double_apply
FAILED test_recording_the_corrected_charge_twice_still_books_it_once
E   Left contains one more item: ('construction', 99)
```

Reverting the identity to the old narrow form makes all three correction
tests fail with `ConflictPayload` from `store.py:285`. No test here passes
vacuously.

## Is a correction a legal concept here

Yes, and it is not a mutation and not a new operation. The docstring at
`trials.py:202` now says so in the model rather than in a review document:

> A charge is a *measurement* of a completed operation, not a fact about
> the operation. […] A correction therefore is not a mutation of the
> original charge, and it is not a second operation either — the operation
> really happened once and its receipts say how much it cost. It is a
> later, better measurement of the same event, and the ledger keeps both so
> that a reader can see that the first reading was superseded.

The operation really happened once. Its receipts are the ground truth.
Two rows pointing at those receipts is a more accurate record than one row
that was wrong and could not be fixed.

## Verification

- `tests/test_s3_trials.py` — 12 passed. All five new tests go through the
  real database, not the mock harness in `test_invl02_accounting.py`.
- `tests/test_invl02_accounting.py` — 12 passed, unchanged.
- `tests/test_s3_experiment.py` — one failure,
  `test_budget_quarantine_cancel_while_dispatched`, asserting
  `INSUFFICIENT_RESOURCES` and receiving `INVALID_INPUT` from `store.reserve`.
  **Not mine**: reproduced identically in a detached worktree at the
  pre-change commit `d9ecb99`. Untouched.

No file under `reports/evidence/` was modified. `reports/evidence/eng-close2/reconciliation.json`
records `expenditure_ledger_sum: 8455`; charges already written there keep
their rows and their old `request_id`s, and a replay of one of them under
the new code would now compute a *different* `request_id` and write a second
row. That is a real consequence of the change for historical data, it is
one-directional (replay of an old charge appends rather than no-ops), and it
does not apply to the smoke script, which only reads.

## Lane conflicts

None. `src/settlement/gateway_http.py` does not reference the ledger.
`scripts/inv01_study.py` shows an uncommitted diff in the shared working
tree; it is another lane's and I did not touch it.
