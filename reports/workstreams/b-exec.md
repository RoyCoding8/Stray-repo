# B-EXEC workstream: shared admitted child path (A1/A2)

Branch `wt/b-exec`, DB `ec02test_bexec`.

Slice 1 (green): `dispatch_admitted_child` in `experiments/coord02/entry.py`
renders the admitted obligation + observations + current bytes, dispatches
ONE broker `MODEL_INFERENCE` call on the configured child model, parses the
`{files, notes}` response, and returns the model bytes. `run_cell` routes
S/A/F/L through `run_child_factory` after admission; the stamp channel
(`admitted_child_factory` + hash-comment append) and the FIXTURE-only
`arm_child_factory` gate are DELETED. `solved_child_factory` remains only
as the explicitly-labeled doubled fallback (FIXTURE label preserved).

Ownership finding (recorded for B-AUTH/B-VERIF): the team submit path
refuses outputs covering paths outside the admitted child's `owned_paths`,
so model repair bytes are owned-partition scoped; the join overlays them on
the snapshot. Full-snapshot model outputs are NOT silently accepted.

Gate: `tests/test_bexec_child.py` (2 tests, red-first) — dispatch-level
verbatim staging + cell-level submit/join with marker-bearing repair bytes.
Existing `tests/test_coord02_exec.py`: 6/8 green on the lane tree; the 2
remaining failures are stale-shape tests (`arm_child_factory` deleted API;
proposal-shaped recording double now refused as non-repair) updated by
B-VERIF, not worked around here.
