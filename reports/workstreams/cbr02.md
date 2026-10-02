# CBR-02 / CBR-03 — held-out freeze RPR-ACQ/2 and full decision rule

Branch `wt/cbr02`, worktree `/tmp/asv2-agenda01/.worktrees/cbr02`.
Gate database `settlement_cbr02` (real PostgreSQL, created for this task).

## Root cause

Two defects, one shared shape: the implementation decided less than the
frozen contract promised. The pilot rule read four quality means while
the frozen `verdict_rule` text promised a
validity/control/quality/resource conjunction, so a synthetic
quality-passing candidate at 1,000,000x baseline elapsed still returned
`promising=true`. And the benefit panel listed seven development plus
two check tasks with zero held-out inputs, so there was no transfer
trial for any rule to decide on. Both reproduced red before the fix
(`/tmp/cbr02_redprobe.py`, throwaway) and green after.

## Changes (owned scope only, no `run.py` edit required)

- `experiments/representation/acquire/panel.py`: `PANEL_VERSION`
  `RPR-ACQ/1` → `RPR-ACQ/2`. New `HELDOUT_SW`/`HELDOUT_GR`
  (`sw-eva-00..07`, `gr-eva-00..07` from the lane B evaluation split:
  held-out seeds and patterns, verified byte-regenerable from
  `splits.generate_*`). `BENEFIT_*` now point at the held-out lists;
  the RPR-ACQ/1 `MECHANICS_*`/`ACQUIRE_*` constants stay for provenance.
  `trial_group` maps held-out tasks to the existing `protected-eval`
  trial group, so no runner or protocol change was needed.
- `experiments/representation/experiment/freeze.py`: `VERDICT_RULE`
  text now states the whole rule: validity/control conjunction,
  1.25x resource bounds with zero-denominator clause, efficiency
  alternative, unknown/missing measurements cannot certify a win, pilot
  does not authorize release.
- `experiments/representation/experiment/checker.py`: `pilot_rule`
  implements the full conjunction (`valid-delivery`, `controls-pass`,
  four quality clauses, per-component `resources-within-1.25x` over
  cpu/elapsed/oracle-queries/model-tokens/exposure with zero-denominator
  handling), the efficiency alternative, per-component unknown tracking
  (missing cpu/exposure block the claim, never become zero), and a
  constant `release_eligible: False`. `_check_costs` additionally
  rejects non-finite/negative measurements; `check_evidence`
  distinguishes unknown improvement/measure values instead of crashing.
  Removed one dead local. `check_all` feeds control results into the
  rule. `replay.py` needed no change: it already prints the full rule
  and accepts `--evidence-root`/`--dsn`.
- `experiments/representation/experiment/manifest.json` +
  `manifest.sha256`: regenerated RPR-ACQ/2 freeze (38 files, 16
  held-out benefit fixtures pinned). `freeze --check` clean.
- `tests/test_rpr11_heldout.py` (new, 14 tests): panel membership and
  trial groups, selectors see development only, eval fixtures
  deterministic, freeze clean plus rule text, 1e6x-elapsed/over-budget/
  unknown/missing counterexamples rejected, zero-denominator behavior,
  full-pass synthetic returns promising yet unreleased, efficiency
  separation, invalid-cost rejection, independent reference
  recomputation (not calling `pilot_rule`), and the real-DB gate below.
- `experiments/representation/evidence-heldout/` (new): gate evidence,
  48 arm-task + 12 control + 2 attribution + 4 use records,
  `index.json`, exact live blocker. No new fixture files were needed:
  the 16 held-out inputs already existed with lane B provenance;
  duplicating them would have weakened the chain.

## Gate output (real PG `settlement_cbr02`, zero model spend)

`replay.py --mode run --tag main` into `evidence-heldout`: 66 ran,
0 skipped. `checker.check_all` clean with and without `--dsn`.
Means: C-transfer 0.153019 vs A/B 0.299312; C-software 0.3688 vs
A 0.731506 / B 0.720142. Resources over 16 benefit tasks: elapsed
C 52.309s vs 0.021s (over); oracle queries C 112 vs A 247 / B 256
(within); model tokens 0/0/0 (within, zero denominator, C also zero);
cpu and exposure unknown in production records (block, never zeroed).
Verdict: `promising: false` (quality fails first; resources independently
fail), `efficient: false`, `release_eligible: false`. The authored core
loses to natives on held-out data — an honest negative, matching the
mechanics result. Live campaign remains exactly blocked
(missing endpoint/key/grant; spent all zero).

## Verification

- `tests/test_rpr11_heldout.py`: 14 passed on `settlement_cbr02`
  (~83s), incl. independent reference agreement on the gate verdict.
- `tests/test_rpr04_freeze.py` + `test_rpr03_acquire.py`: 16 passed,
  2 skipped. `test_rpr05_runner`: passed.
- Lint: no new findings under the repo rule set (line-length clean;
  remaining hits are pre-existing file patterns).

## Known fallout for the coordinator (not touched: outside owned scope)

- `test_rpr08_evidence.py::test_full_panel_is_checker_clean` asserts 27
  benefit records (now 48); `test_committed_evidence_is_checker_clean`
  reads `evidence/` (RPR-ACQ/1 bytes, old manifest sha → drift under the
  RPR-ACQ/2 freeze). Both need migration to the two-freeze layout.
- `test_rpr06_transfer.py` (2 tests) drives `run_benefit_pair` on
  `gr-che-00`, which the RPR-ACQ/2 manifest no longer pins → KeyError.
  Retarget at held-out tasks or pin RPR-ACQ/1 bytes for that regression.
- `test_rpr07_resume.py::test_fresh_database_is_not_resume` fails
  identically on the unmodified base (DROP/CREATE DATABASE through this
  connection) — pre-existing, environmental, unrelated.
- Record `stage` for held-out rows still reads `mechanics`: `run.py`
  derives it from the RPR-ACQ/1 acquire lists and was left untouched per
  scope. Cosmetic only (benefit accounting and `protected-eval` trial
  routing are correct); runner owner can relabel.
- Production records carry no `cpu_s`/`exposure_units`: the rule
  correctly blocks resource certification until the runner measures
  them. Wiring real CPU/exposure accounting belongs to the runner
  owner; the checker seam (`_component_value`) already reads them.
- Default `replay --mode check` still points at `evidence/`
  (RPR-ACQ/1, now red under the new freeze); use `--evidence-root
  experiments/representation/evidence-heldout` for the RPR-ACQ/2 gate.
