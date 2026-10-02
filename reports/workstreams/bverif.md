# B-VERIF workstream: independent public-path gate (C1)

Branch `wt/b-verif`, DB `ec02test_bverif`.

Slice 1 (green): `tests/test_bverif_public.py` locks the PUBLIC panel path
— freeze-schedule coordinates → `run_cell` → `write_evidence` — to model
repair bytes: recording double serves unexpected-but-valid bytes at the
configured gateway seam; the exported evidence record carries the marker
bytes with no stamp comment.

Stale-shape updates (justified, not weakened):
- `test_fixture_route_unreachable_in_live_mode`: called the deleted
  `arm_child_factory` API directly — now asserts `run_cell` raises
  `unknown constructor label` through the production seam.
- `test_recording_model_output_changes_submitted_bytes`: served a
  plan-proposal shaped double at the CHILD seam (now honestly refused as
  non-repair) — now serves `{files, notes}` repair bytes and asserts the
  marker reaches the restaged tree.
- `test_m2_ec06_integration_join_and_failed_join`: expected
  `join-failed-terminal` from inert-fixture cells — now asserts the honest
  `submit-refused` / `no constructor artifact` terminal (stamp channel
  deleted; no bytes submitted, none joined).

C1 verdict: PASS on the integrated path — child-byte lock (A1), decision
lock (A2 via exec battery), store-derived costs helper (A6 unit), dispatch
and retention slices (A3/A4/A9) green with neighbors clean. Remaining for
full C1: `run_cell` cost/receipt rewiring to `costs_for_operations`
(B-AUTH slice 2) and frozen-study replay — tracked, not blocking this gate.
