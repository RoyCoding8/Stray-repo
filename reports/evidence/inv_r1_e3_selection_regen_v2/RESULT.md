# Regeneration V2: the E3 store witness, the namespace ledger, and the ladder marker

Three artifacts, each produced by a committed script, none of them overwriting
anything that already exists.

| | |
|---|---|
| generator | `experiments/regen_v2/regen_e3_store_witness.py` |
| underlier | `experiments/ad01/s09_e3_selection.py:419` `store_witness`, via `write_sever_evidence` at line 517 |
| artifact | `e3-store-witness-v2.json` |
| write-up | `reports/STAGE-09-EVIDENCE-FINDINGS.md` |
| live dispatches | **0** |
| replaces | `reports/evidence/inv_r1_e3_selection/e3-store-witness.json`, `.../e3-sever-control.json` |

`experiments/regen_v2/regen_e3_ladder_status.py` writes
`reports/evidence/inv_r1_e3_ladder/committed-ladder-status.json` and
`reports/evidence/inv_r1_e3_ladder/RETRACTED.md`, for B6 / N-80.

Both scripts read an isolated, migrated, disposable database named per run
rather than a hardcoded one, because every worktree on this cluster shares one
PostgreSQL and a hardcoded name is dropped by any concurrent run.

## What changed

| | committed witness | this artifact |
|---|---|---|
| connected `bindings` | 5 | 5 |
| connected `receipts` | 5 | 5 |
| connected `operations_written_by_the_run` | **0** | **5** |
| connected `operations_in_store` | **0** | **5** |
| severed `bindings` | 0 | 0 |
| severed `receipts` | **4** | **0** |
| severed `operations_written_by_the_run` | 0 | 0 |
| severed `operations_in_store` | 0 | 0 |

Two contradictions closed, and they had **different causes**, which is the part
worth being precise about.

**The severed arm was a generator defect.** `bindings` was the only source of
the receipt id list, so severing it emptied the list handed to `read_back`
while receipts already in flight still landed. The current generator derives
`receipts` from `run.operations` at line 501, and `read_back` short-circuits on
an empty list at line 390, so `bindings: []` and `receipts: []` now travel
together.

**The connected arm's `0` was a sampling-order defect, and regeneration alone
would not have fixed it.** At `52235a6` the count was taken at line 529, the
run at line 530, the count again at line 532, and the binding loop that actually
wrote came after at line 534. A correct run of that generator produces `0`, so
the committed value is not evidence of a hand edit. HEAD moved the writes
inside the run, and the count now reads `5` against its own 5 receipts. The
write-up predicted this half would remain open; it is closed, but by a later
commit, not by the regeneration.

## The invariants are checked, not asserted

The committed artifact failed three of these at once, and a field that cannot
fail is not evidence. Each is evaluated per arm, because an invariant scoped to
one arm scored on the other is a false alarm rather than a check.

```
every_consistency_check_holds: true
run_digest_disambiguates:      true
```

## B5: one namespace, one current witness

`measure_digest` cannot discriminate runs. It is
`selection.yield_measure_digest()`, the frozen measure set, so it is identical
across every artifact of the study **by construction**. Making it vary would
change what it measures, and the measure set is frozen by design.

So the artifact publishes `run_digest` beside it, over the run's own operation
ids. The two arms' digests differ, and both are in the file. The
`namespace_ledger` block names which file is current, which two it supersedes,
and which is annotated rather than superseded.

`e3-admitted-operations.json` is **not** superseded. It is a descendant commit
reporting `5` where the witness reported `0`, and this artifact agrees with it,
so the succession is settled by measurement rather than by commit order.

## What this does not fix

- `measure_digest` is still shared. `run_digest` is the field that varies.
- `operations_in_store` is scoped to this run, so it cannot see a foreign
  lane's row. That is the N-301 correction. A study-wide number needs the
  prefix-filtered count `experiments/ad01/e3_ladder.py:453` `store_verdict`
  uses, and that number carries its own caveat: 84 by durable-name-prefix
  against 42 the store's own contamination walk sees.
- Nothing here retracts `e3-crossover.json`. That is N-80, covered by
  `../inv_r1_e3_selection/RETRACTED.md` cause 1, and the ladder embedded in the
  post-fix file is annotated in `../inv_r1_e3_ladder/`.

## Reproducing

```
createdb "$(printf 'regenv2_%s' "$(head -c6 /dev/urandom | od -An -tx1 | tr -d ' \n')")"
export SETTLEMENT_TEST_DSN="postgresql:///<that name>"
.venv/bin/python -m settlement.db   # or: apply migrations via settlement.db.apply_migrations
.venv/bin/python -m experiments.regen_v2.regen_e3_store_witness
.venv/bin/python -m experiments.regen_v2.regen_e3_ladder_status
```

Operation ids carry a uuid per run, so the per-row bytes differ between runs
while every count, invariant and digest relationship above reproduces. The
digest relationships are what this artifact claims, and they are what a
reviewer should check.
