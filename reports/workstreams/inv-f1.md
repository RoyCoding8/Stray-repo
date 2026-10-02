# INV-F1: canned constructor seam refuses unattested artifacts

Worktree `.worktrees/inv-f1`, branch `wt/inv-f1-seam`. Disposable database `inv_f1_seam`, dropped after validation.

## Root cause

`dev_constructor` (`experiments/coord02/experience.py`) and `solved_child_factory` (`experiments/coord02/entry.py`) authored child bytes straight from oracle snapshots and overlays. No committed driver calls either factory. Every byte through them skipped broker admission, so episodes reached `success` with zero `model-inference` operations.

## Fix

Both factories now return `None` from the built constructor. The controller already maps that to `submit-refused` with reason `no constructor artifact for <node>` and a `constructor` liability. The names stay importable. The admitted path (`run_child_factory` via `dispatch_admitted_child`) is untouched. Net deletion across the two files.

## Evidence

Red before the fix: `tests/test_inv_f1_seam.py::test_canned_constructors_refuse_without_admission` failed with the constructor returning authored `src/*.py` bytes instead of `None`.
Green after the fix: `tests/test_inv_f1_seam.py` passes 2 of 2, including an episode-level test asserting `submit-refused`, the `no constructor artifact` reason, and a `constructor` liability.
Nearby: `tests/test_inv_b3_coord02_contracts.py` passes 7 of 8. The one failure is `test_canned_seam_carries_no_admission`, which pins the old unattested-success behavior and now observes `submit-refused`. That test is outside this scope. Collection over the seven coord02 suites touching the seam gathers 114 tests with imports intact.
