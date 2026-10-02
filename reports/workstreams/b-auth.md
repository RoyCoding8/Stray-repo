# B-AUTH workstream: op projection + budgets + resume

Branch `wt/b-auth`, DB `ec02test_bauth`. Base merge-tip `4b5cb99`.

## Slice 1 (green): store-derived cell costs — commit `ae98333`

- New test `tests/test_bauth_evidence.py` (1 test): seeds 2 settled broker
  MODEL_INFERENCE ops with nonuniform usage (7 in/11 out, 13 in/29 out),
  asserts `costs_for_operations(dsn, op_ids) == {in: 20, out: 40, calls: 2}`,
  plus shared-op-counted-once (`[op1, op1, op2]` same union). Failed red
  (`AttributeError`) before implementation.
- New `schemas_evidence.costs_for_operations(dsn, op_ids)`: reads receipt
  `usage` rows from the DB, dedups shared ops, sums input/output/calls;
  unknown (no measured usage) raises `TrialError` — unknown stays unknown,
  never a constant.
- Extracted `_full_usage(receipts)` shared with
  `operation_record_from_store_row` (behavior-preserving; strict all-fields
  check replaces the old partial-pick loop).
- Preservation: `test_coord02_state.py` + `test_coord02_ecr202.py` 24 passed
  on their own DBs. `run_cell` rewiring is slice 2 (B-EXEC-owned entry.py,
  untouched).

## Next slices (not started)

- Slice 2: rewire `run_cell` to `costs_for_operations` (needs B-EXEC seam).
- A7 resume / A8 eligible-repair acquisition in `experience.py`.
