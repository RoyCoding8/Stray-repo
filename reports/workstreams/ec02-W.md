# EC02 lane W — workload, protected oracles, freeze, offline checker

Base: `d9795b6`. No commits yet at report time; takeover state noted below.
DB: `ec02test_w` (host `/var/run/postgresql`, user `ubuntu`).

## Takeover provenance

Lane-W writer failed mid-flight (provider-side streaming error, not a
repo problem). Coordinator took over inline in the same free worktree
(no writers running, no stand-down needed). All work below is the
writer's except where marked COORDINATOR.

## Contents (`experiments/coord02/`)

- `corpus/generate.py`: deterministic generator for 30 tasks in 6
  families (`sep` t01-t05, `cpl` t06-t10, `dia` t11-t15, `sng`
  t16-t20, `rw` t21-t25, `sco` t26-t30), each 2 dev + 2 eval + 1
  transfer (`SPLITS`: 12 dev / 12 eval / 6 transfer). Writes
  `corpus/tasks/<id>/{spec.json,spec.md,public.json,src/**}`,
  `protected/<id>.json`, `protected/reference/**`, plus `oracle.py`
  self-pin, `manifest.json` + `manifest.sha256`.
- `oracle.py`: per-family public/protected splits, reference
  implementations, `run_candidate`/`evaluate_tree` (real subprocess),
  `prepare_tree`/`partial_tree`/`observe`/`implicate`/`stale_after`/
  `check_binding`, `build_solver_payload` (proven protected-free),
  `task_input_digest`, per-task fixtures.
- `freeze.py`: `build_freeze`/`write_freeze`/`verify_freeze`,
  counterbalanced schedule (30 tasks x 4 arms x 2 repeats = 240
  cells), `CEILINGS`/`RULES` from the cap sheet, pinned-hash drift
  detection (corpus manifest, oracle, checker, schedule, budgets,
  rules).
- `checker.py`: `make_record` (canonical evidence builder),
  `check_evidence` (offline rederivation + tamper detection:
  deleted cells/pairs, cross-panel collisions, wrong
  procedure/input digests, altered/unattributed receipts,
  ceiling breaches, verdict/tally mismatches), `_cross_check_receipts`
  (DB-anchored receipt verification), `summarize`, CLI main.

## Pressure coverage (each proven positive + negative in tests)

- sep: first-two-files shortcut fails (t01-t04 graded outputs need
  all four modules); t05 conversion pair shares rounding/boundary.
- cpl: locally-plausible single-stage output fails combined checker
  (t06-t09 producer+consumer; t10 three-stage chain).
- dia: observation changes the justified choice; fault isolated to
  one module; t15 carries cross-module deps (no hidden labels).
- sng: strong single fits envelope; t20 delegated topology still
  needs both edits.
- rw: genuinely-reusable AND actually-stale rework cases both exist
  (`stale_after` via convention diff + dependent closure).
- sco: explicit incompatibility/refusal AND legitimate renamed use
  both exist (`check_binding`: renamed-compatible binds,
  incompatible/missing declines, version/quarantine blocks).
- Transfer: t05/t10/t15/t20/t25/t30 change topology/role-mapping/
  semantics beyond values/names; t15+t30 combine previously-separate
  pressures.
- Separation: `test_no_protected_leakage_into_solver_payload` proves
  no protected payload/reference/checker bytes in solver inputs.

## Coordinator fixes (post-takeover)

- F-EC02-W01 (stale oracle pin): `oracle.py` read twice by
  `build_all` (once for the file entry, once for
  `evaluator.code_digest`); an oracle edit between generation and
  the test run broke `test_corpus_inventory`. Fix: single
  `oracle_raw` read reused for both pins. Verified: regen, then
  17/17 green.
- Slop pass: folded `_manifest` hash check into shared `_pinned` /
  `_pinned_dir` helpers; removed unused `CEILING_FIELDS` map.
  Oracle preservation: full 17-test file green before and after.

## Gate

`tests/test_coord02_workload.py`: **17 passed** on real PostgreSQL
(`ec02test_w`) + real subprocesses, no model calls. Includes
fresh-checkout reproduction (`generate` from tracked files only;
manifest self-hash verified).

## Interfaces for lanes L / E

- Dev tasks: `oracle.SPLITS["development"]` (12 ids); eval:
  `oracle.SPLITS["evaluation"]`; transfer:
  `oracle.SPLITS["transfer"]`.
- Solver inputs: `oracle.build_solver_payload(task_id)` (protected-free).
- Observation/diagnostics: `oracle.observe(task_id, payload)`,
  `oracle.implicate(task_id)`, `oracle.stale_after(...)`,
  `oracle.check_binding(task_id, profile_id)`.
- Freeze: `freeze.build_freeze(freeze_id, source_sha=..., package=...,
  baselines=..., model=..., config=...)`; verify with
  `freeze.verify_freeze(path)`.
- Evidence: `checker.make_record(freeze, evidence_root, panel=...,
  task=..., repeat=..., arm=..., costs=..., receipts=...)`;
  audit with `checker.check_evidence(evidence_root, freeze_path,
  dsn=..., receipt_table=...)`.
- Pair identity: `(freeze_id, panel, task, repeat, arm)`.

## Limits

- No live model calls were made or needed (doubles only where the
  harness needs a gateway; none in this lane's tests).
- Corpus feasibility calibrated on development tasks only
  (`test_baseline_feasibility_on_development`).
- Arm treatments (S/A/F/L) are lane E's property; this lane only
  defines task pressure + verification.
