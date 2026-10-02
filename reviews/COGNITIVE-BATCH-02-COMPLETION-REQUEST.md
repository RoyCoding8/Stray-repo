# Review request — Cognitive Batch 02 live2 completion

To: design/review role. From: worker (Nightjar).
Branch: `codex/implementation-cognitive-batch-02` (lane `wt/live2` merged).
Scope: CB2-01–03 closure and the live2 campaign (86 live episodes).

## What to check

1. CB2-01: `experiments/team01/solver.py` — every S/P/T repair call
   goes through the live gateway; scored trees assemble from submitted
   bytes only (`_final_tree_live`); no reference overlays in the
   solver path; prompts carry no family/kind labels.
2. CB2-02: `experiments/team01/acquire2.py` — no authored menu; the
   directive is model text from dev records; freeze selects one
   validated build or explicit `none`.
3. CB2-03: `experiments/team01/evidence-live2-panels/` — 86 episode
   records plus builds, ledger, frozen template, verdict, replay,
   reconciliation and check-all review; fresh checkout recomputes the
   same verdicts without a provider or DB.
4. Apparatus fixes and their tests: refused-usage accounting and
   `replay_panel` live-shape guards in `solver.py`/`checker.py`;
   `tests/test_team_solver.py` (16 tests) covers both.
5. Honest negatives: eval `beats-S` false (tool ratio), transfer ties,
   t09 join rejections, t06-S-r2 refusal with retained pre-fix usage
   record. Confirm nothing here should have been re-run or smoothed.

## Results

- Full suite: 895 passed, 0 failed (PostgreSQL, ~43 min).
- Panels: eval T 16/16 vs S 15/16 vs P 16/16; transfer 8/8/8; neither
  panel promising — null team-benefit result, reported as such.
- Spend within all declared caps; reconciliation 85/86 with zero
  missing receipts.

Full detail: `reports/TEAM-01-LIVE2-PANELS.md`. CB2 dispositions and
live rows: same report plus `reports/TEAM-01.md` (LIVE-03b–07b).
