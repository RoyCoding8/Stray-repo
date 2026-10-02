# M2: the construction join closes, the use join is not recoverable

Lane AA4. Answers the question `b13e5e0` left open: can the three use-phase
operations be reconstructed from what was committed, or is the evidence gone.
It is gone, and this records what that means and what would have to change.

Read: `WORKER-STAGE-09-CONNECTED-STUDY.md:51` and `:53`, the committed
`reports/evidence/inv_r1_m2_join/`, and the source path that mints and
dispatches a use operation. Nothing under `reports/evidence/` was modified.
Nothing was run against a gateway. The two stores named below were queried
read-only for existence.

## 1. The answer

**The three use operations cannot be reconstructed.** Not "not yet found" and
not "would need more search". The fields a receipt is made of were never
written to anything committed, so no amount of reading the repository
recoveries them.

The acquisition side of line 53 does close. 71 operation rows each join to
their own receipts, both acquired methods join to the model call that wrote
them, and every digest is recomputed rather than trusted. That work is
`b13e5e0` and it is not re-litigated here.

The use side of line 53 does not, and cannot, be closed from this repository.

## 2. What a use receipt is made of, and what is committed

`method_exec.run_member_out_of_process` reaches
`broker.dispatch_operation`, which persists a receipt. For the local launcher
that receipt's payload is built at `src/settlement/launcher_local.py:553`:

```python
data: dict[str, Any] = {"stdout": stdout, "returncode": returncode,
                        "timed_out": timed_out, "wall_ms": wall_ms}
if stderr: data["stderr"] = stderr
```

with a `launcher_id` and a `profile` alongside. So a use receipt holds the
child process's raw stdout, its exit status, whether it timed out, how long it
ran, and its stderr.

The three executed use records in
`reports/evidence/inv_r1_m3b/use_records.json` carry 20 fields each, including
a parsed `output` object. Measured:

```
ad01-w2-I-00-I-ad01-w2-within-sw-00        output present, no stdout/stderr/returncode
ad01-w2-I-00-I-ad01-w2-within-sw-01        output present, no stdout/stderr/returncode
ad01-w2-I-00-I-ad01-w2-transfer-sw-00      output present, no stdout/stderr/returncode
```

What is committed is the *post-parse* result. What a receipt is made of is the
*pre-parse* process observation. The parse is lossy and the direction is
irreversible: `output` cannot produce the stdout that produced it, and the
three fields with no counterpart at all are `returncode`, `timed_out` and
`wall_ms`. A receipt reconstructed from `output` would not be a receipt. It
would be a fabrication wearing a receipt's field names, which is the specific
thing line 53 forbids and the thing the 5563-unit history already went wrong
once.

## 3. The receipts existed, and the store is gone

The operations are not fictional. `selection.versioned_use_op_id` mints them,
`trajectory.py:1481` passes them to `method_exec.run_member_out_of_process` as
`operation_id`, and that path calls `broker.ensure_operation` and
`broker.dispatch_operation` and persists. The receipts were written.

The two stores that hold them were dropped at teardown and are not on the
cluster. Queried read-only just now:

```
select 1 from pg_database where datname='s09iso_m3run7_c4642aac7359'  ->  ABSENT
select 1 from pg_database where datname='s09iso_m3run8_ef70d43f4552'  ->  ABSENT
```

Every export was written during the trajectory phase, before the use phase ran,
so none contains a use-phase row. A search of every file under
`reports/evidence/` for the three operation ids returns three files, and all
three are the `b13e5e0` join output and its prose:

```
inv_r1_m3b/use_records.json      (the records that name the operations)
inv_r1_m2_join/join.json         (which records the absence)
inv_r1_m2_join/RESULT.md         (which says the absence)
```

A file containing both a use operation id and any receipt-bearing field
anywhere under `reports/evidence/` is `join.json` alone, and in it those
operations appear precisely as the rows that have nothing to join.

## 4. The precise scope of the gap

3 of 60 use records name a method. All 3 lack a receipt. The other 57 were
refused before execution, so they have nothing to join and their absence is
correct rather than a loss.

Run 7 and run 8 each contributed exactly one executed use. Run 7's
`use_records.json` has 24 records, every one with `executed: "refused"` and
`operation_ids: []`, which is why the 24 count above is refusals and not
executions.

So the honest statement of line 53's state is: **the join between a task
method and its own receipt is complete for acquisition and absent for use, and
the use receipts are not reconstructible from committed bytes.** That is a
property of what was kept, not a gap in the work that was done.

## 5. What it would take to have it next time

The fix is one export, and it is a small one. Nothing about the execution
boundary or the receipt format needs to change.

**Export the receipt table at the end of the run, while the store exists.**
`store.operation_receipts(dsn, operation_id)` at
`src/settlement/store.py:2102` is already the read. What is missing is a call
to it for use-phase operation ids at teardown, in the same pass that already
writes `operations` and `unknown_exposure` into each export.

The exports carry `operations`, and the run 8 exports have 2 to 8 rows each,
all construction and validation. The use-phase operations were minted after
the last export was written. So the shape is already there and the rows are
simply absent.

Three things that would make the next run's use join close:

1. **Re-export after the use phase, not only during the trajectory phase.**
   The existing export covers the construction chain completely and stops
   before the use chain starts.
2. **Include `stdout`, `returncode`, `timed_out` and `wall_ms` verbatim.**
   The parsed `output` is a legitimate finding and is already committed. The
   receipt is a different artifact and none of its four process fields is
   derivable from it.
3. **Write the use-phase operation ids into the export's `operations` list.**
   `join.json` currently learns about them only because a use record names
   them, which is why the absence is documented as a search result rather than
   as an export schema fact.

If those three land, the same `s09_m2_join.py` joins the use phase with no
change to itself, because it keys on `operation_id` and reads receipts
whichever export carries them.

## 6. What this is not

**This does not close SWE transfer.** `WORKER-STAGE-09-CONNECTED-STUDY.md:47`
puts actual SWE transfer outside M2's scope and says two toys do not close it.
Nothing here changes that. The reload proof reproduces three executions of one
method on two within-world tasks and one same-world transfer task. That is a
durability result, not a generalisation result, and no receipt would change it.

**No receipt was manufactured.** No file under `reports/evidence/` was written,
modified or deleted. `inv_r1_m2_join/` is exactly as `b13e5e0` left it.

**No claim about acquisition yield.** Run 8's 30 model calls and 36 use records
are dominated by 33 refusals, which its own `RESULT.md` attributes to empty
repertoires and one scope mismatch. That is a yield measurement and it is a
different question from whether a receipt exists.

## 7. One adjacent defect, recorded and not fixed

`reports/evidence/inv_r1_m3b/repertoires/control-sw.json` declares two members
with different `source_digest` values and byte-identical `method_source`, and
neither digest matches `sha256(method_source)`. Already recorded as N-77 in
`reports/STAGE-09-RETIRED-EVIDENCE.md` and carried forward by `b13e5e0`. Not
re-verified here beyond noting that `b13e5e0`'s `join.json` still reports
`byte_identity_verified: false` for both. Any future acquired-versus-control
comparison has to join on more than the source digest, because the control arm
is not byte-distinct from the acquired arm.
