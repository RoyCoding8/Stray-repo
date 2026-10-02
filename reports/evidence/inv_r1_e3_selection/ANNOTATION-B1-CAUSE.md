# B1 / N-300 — the severed arm's four receipts were **made**, not orphaned

Second pass on B1. `ANNOTATION-B1-B5.md` in this directory gives the cause as
*"`bindings` was the only source of the receipt id list, so severing it emptied
the list passed to `read_back`."*

**That is wrong, and it is wrong in the direction that matters.** Under that
cause the receipts should never have been written. They were written. Both
halves of the state are reachable, the defect is in the return expression rather
than in the loop, and the correction changes what the artifact records.

The existing annotation is left as it is. It is one of the four findings this
row is about, and it is not wrong about the artifact, only about the cause.

## What is true

`bindings` was never the only source of the receipt id list. At `52235a6`,
`store_witness` built the list from `bindings`, and the loop that fills
`bindings` had **no `sever` guard at all**. Read at that commit:

```python
# s09_e3_selection.py:534, unmodified at 52235a6
bindings, refused_operations = [], []
for seq, execution in enumerate(run.executions):
    ...
    ensured = broker.ensure_operation(...)
    if ensured.code not in (ResultCode.APPLIED, ResultCode.ALREADY_APPLIED):
        refused_operations.append({...}); continue
    status = broker.dispatch_operation(...)
    receipts = store.operation_receipts(dsn, operation_id)
    bindings.append({... "settled": bool(stored.get("settled")), ...})
```

The loop runs on `run.executions` in both arms. Severing the decision consumer
changes what the executions *do* (every one takes the `no-candidate` fallback,
which is why all four `refused_decisions` carry a populated
`fallback_reason` and `"operation_id": ""`), and it does not stop the loop from
binding each one to a real operation through the real broker. So the severed arm
made four operations, dispatched them, and got four `success` receipts. Measured
from the committed file: all four severed receipts carry
`receipt_identity: "inline:<operation_id>"` and `outcome: "success"`, against
four distinct operation ids in the `ad01-e3sever-cut-*` namespace.

`sever` was then applied **only at serialization time**, and asymmetrically:

```python
"bindings": [] if sever else bindings,                                    # :609
"receipts": read_back(dsn, [b["operation_id"] for b in bindings]),       # :611
```

Line 609 hides the local list. Line 611 reads the local list, which is still
full. That single asymmetry is the whole defect. The state is not unreachable at
all: it is what a generator that hid its bindings but not its receipts produces,
which is exactly what the file contains.

This is confirmed by the artifact against its own generator. `read_back`
short-circuits on an empty id list:

```python
# s09_e3_selection.py:462
def read_back(dsn, operation_ids):
    rows = []
    if not operation_ids:
        return rows
```

A run of `52235a6` as committed could not have produced four severed receipts.
It would have produced `bindings: []` and `receipts: []`. **The committed file
and the commit that introduced it disagree**, which is the strongest form this
defect can take: the artifact is not a corrupted record of a run, it is a record
the committed code cannot produce.

## The second half, corrected

`ANNOTATION-B1-B5.md` is right that `operations_written_by_the_run: 0` beside
five receipts was a sampling-order defect at `52235a6`, where the count at line
532 ran before the writes at line 534. Verified by reading that commit.

The severed arm's `operations_in_store: 0` is the **same asymmetry again**, and
the same correction applies. It is `wrote`, measured by the delta around
`run_policy` only, and `run_policy` at `52235a6` took no `dsn`, so the run
persisted nothing by that measure. The four operations the loop then created
were never counted. The connected arm's `0` has the same cause. Both numbers are
under-counts of the same kind, and both are fixed at HEAD by the same change,
which is that the writes moved inside the run.

## What this does not change

- The artifact is still wrong and is still not edited. `e3-store-witness.json`
  and `e3-sever-control.json` keep `bindings: []` with four receipts.
- The `_regen_v2` replacement is still the right artifact. It records
  `severed.bindings: 0` **and** `severed.receipts: 0`, which is the reachable
  state, and it does so because HEAD's generator derives receipts from
  `run.operations` and returns early on an empty list. The two now travel
  together because the loop is now guarded, not because the return expression
  was fixed.
- Nothing in the study's claims moves. The severed arm wrote four operations
  either way; what the artifact misreports is that it wrote none.

## The rule this is an instance of

A counterfactual field and its measured field must not be serialized from
different sources. `"bindings"` was documented at the time as
*"a counterfactual"* and `operations_in_store` as *"what the study persisted,
which bounds the claim"*. The artifact gave the counterfactual a value of `0`
and the measurement a value of `0`, while a third field carried the truth. Three
fields, one underlying state, no invariant tying them.

The check that would have caught it is a reachability assertion, not a
consistency one: for every arm, the receipt set is derivable from the binding
set, and a non-empty receipt set implies a non-empty operation set. Nothing in
the generator or the tests asserts either.
