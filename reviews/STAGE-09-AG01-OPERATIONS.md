# Stage 09 AG01: a charge is not an operation

Scope: `experiments/agenda01/runner.py::AgendaBackend.charge_aux`, and the four
tests added in `tests/test_ag01_experiment.py` to pin it. Follows C23
(`2b092a6`, `f83c700`), which made `store.reserve` refuse an `operation_id`
that is not already a row. That change moved the 18 AG01 failures one command
earlier without moving the count: the signature went from
`settle eval-final refused` to `reserve eval-final refused`.

## The defect

`charge_aux` minted `op_id = f"ag01:{traj}:{label}"`, reserved against it, and
settled it. There is no `INSERT INTO operations` anywhere under
`experiments/`, so that id was never a row. Before C23 the dangling reference
was tolerated and the charge landed. After C23 the reserve refuses it, which
is correct: a reservation naming an operation that does not exist can never be
settled or released, so committing it spends authority on exposure nothing can
close.

## The decision: Shape B, with the charge keeping its own identity

Shape B, in the exact form `agenda._agenda_charge_decision` already uses: the
charge reserves and settles in one transaction on a private identity, without
naming an operation. It is safe because a charge is not an operation — nothing
is dispatched, no adapter runs, and no receipt is ever written — so the
reconciliation path that required the operation was never the one closing it.

Shape A is the wrong shape here, and the reason is not a cost tradeoff. It is
that Shape A is *detectable as a defect by the checker that validates these
traces*. `checker.check_trace` requires every `operations` row in the ledger to
carry a receipt:

```python
receipt_ops = {r["operation_id"] for r in ledger.get("receipts", [])}
for op in ledger.get("ops", []):
    if op["id"] not in receipt_ops:
        reasons.append(f"effect-without-receipt {op['id']}")
```

`export_ledger` selects `operations WHERE id LIKE 'ag01:{traj}:%'` — the exact
namespace `charge_aux` writes into. An `eval-final` operation row would
produce no receipt, so every trace would report `effect-without-receipt`. The
18 failures would not reach zero; they would change shape, which is the outcome
this review is required to reject. The same test is what the Shape A mutant
below is run against, and it goes red exactly there.

Shape B taken literally — reserve with an empty `operation_id` — is also wrong,
and for a different reason. `checker._union_spent` adds settled cost **by
operation id**, so N distinct recovery drains sharing the empty string collapse
into one union key and the spend is under-reported. That is the exact tamper
the checker exists to reject, and it would be a silent one. So the charge keeps
`charge_id` in `reservations.operation_id`; it just is not a row in
`operations`, which is what the column's empty-string sentinel was already
reserved for.

## The fix

`charge_aux` now goes through `store.transact` — the public door, not a private
helper — taking the reservation and the settle in one journaled command:

```python
def _fn(cur, control):
    store._take_reservation(cur, allocation_id, res_id, int(amount), charge_id)
    store._settle_amount(cur, res_id, "success", int(amount))
    return (ResultCode.APPLIED, f"charged {amount}",
            {"charge_id": charge_id, "amount": int(amount)}, [], [])
```

Two properties fall out of that choice rather than being asserted beside it.
The command is journaled, so a replayed charge returns `ALREADY_APPLIED` and
debits once — the same idempotence `store.reserve` gave the old code for free.
And because `_take_reservation` raises `InsufficientResources`, an overdraft
rolls the whole charge back and spends no exposure; the old two-command version
could have reserved and then failed to settle.

## Red before green

Each of the four new tests was run against a deliberately broken
`charge_aux`, and against the fix.

**Shape A mutant** (charge mints a real operations row via
`store._prepare_operation`), against
`test_charge_aux_books_a_charge_and_no_operation`:

```
>           assert backend.operation(charge_id) is None, \
                "a charge that is never dispatched must not be an operations row"
E               AssertionError: a charge that is never dispatched must not be an operations row
E               assert {'id': 'ag01:scratch-charge:eval-final', 'attempt_id': None, 'dispatch_state': 'prepared', 'payload': {'effect': 'charge', '_authority_version': 1}} is None
E                +  where {'id': 'ag01:scratch-charge:eval-final', ...} = operation('ag01:scratch-charge:eval-final')
tests/test_ag01_experiment.py:962: AssertionError
1 failed, 40 deselected in 14.80s
```

**Empty-`operation_id` mutant** (literal Shape B), against
`test_charge_aux_distinct_charges_do_not_collapse` and the same test as above:

```
>           assert settled == 2, \
                f"two distinct charges must total 2, got {settled}"
E               AssertionError: two distinct charges must total 2, got 1
E               assert 1 == 2
tests/test_ag01_experiment.py:1002: AssertionError
FAILED tests/test_ag01_experiment.py::test_charge_aux_books_a_charge_and_no_operation
FAILED tests/test_ag01_experiment.py::test_charge_aux_distinct_charges_do_not_collapse
2 failed, 39 deselected in 22.75s
```

With the fix restored, all four pass:

```
....                                                                     [100%]
4 passed, 37 deselected in 5.24s
```

Three entry points are asserted separately, because they agree only while the
charge stays a charge: the direct `backend.operation()` read, the reservation's
own `operation_id`, and the checker read over the exported ledger. A first
version of the C23 suite passed 6/6 with its guard in the wrong place because
every case went through one public door; these deliberately do not.

## Verification

`tests/test_ag01_experiment.py`, `PYTHONPATH=.:src`, 196s before, 244s after
(split into two halves, disjoint selectors, 23 + 18 = 41 collected, no overlap):

- before — `18 failed, 19 passed in 196.90s (0:03:16)`
- after, first half — `1 failed, 22 passed, 18 deselected in 113.81s (0:01:53)`
- after, second half — `1 failed, 17 passed, 23 deselected in 130.28s (0:02:10)`

**39 of 41 pass. The 18-failure set is down to 2**, and both residuals were
proven pre-existing by running each against a byte-for-byte copy of the
unmodified HEAD `runner.py`, restoring my version afterwards.

The two that remain do not touch `charge_aux` and were not caused by this fix:

1. `test_duplicate_outoforder_wakeup_single_effect` — asserts
   `backend.dispatch_probe(op).sent_this_call`, and the operation is already
   `dispatch_state='observed'`, so the send happened on an earlier call. Against
   unmodified HEAD: same `AssertionError: assert False`, same
   `DispatchStatus(..., dispatch_state='observed', ..., sent_this_call=False)`.
2. `test_duplicate_effect_decisions_charged` — `_dispatch_launch` raises
   `dispatch ag01:w08v0_r_t0:probe:7 left receipts missing:
   ['w08v0_r_t0:rc:att-s-deep-deep:p3']`. Against unmodified HEAD: byte-identical
   message, same operation, same receipt.

Neither is a reservation-naming-an-operation failure, and neither reaches
`charge_aux`. They are a dispatch/receipt-accounting pair, in the store and
broker, and out of this lane's owned paths.

## Cost


- `experiments/agenda01/runner.py` — `charge_aux` only, +32/−12.
- `tests/test_ag01_experiment.py` — four tests appended, no existing test
  modified.

Nothing under `src/settlement/**`, `experiments/ad01/**`, `scripts/**` or
`migrations/**` was touched, and no store change is needed or requested.

## Open, not fixed

`export_ledger` still queries `operations` for the `ag01:{traj}:%` namespace and
returns only probe operations, so `ledger["ops"]` never carries a charge. That
is now correct rather than accidental, but the ledger is asserting something
about charges implicitly. A future reviewer asking "which charges does this
trace contain?" must read `reservations`, not `ops`. Worth a name, later,
outside this lane.
