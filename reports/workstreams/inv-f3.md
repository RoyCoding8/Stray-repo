# Investigation lane F3: report-level corrections (worktree inv-f3)

Base `804940d` on branch `wt/inv-f3-reports`. Scope is this note plus the two one-line-class corrections below. No `src`, `experiments`, `tests`, `scripts`, `pyproject`, lock, or `evidence*/**` path touched. No Postgres used.

## Corrections

INV-E-01 (plus INV-R-T03, same split). Stated one definition for resume counts and corrected the outlier in place. Calls means durable model-inference operations, `accounting.total.model_calls` in each `evidence-ad01/c4-live/<trace>.json`. `resume-w0-R.json` holds top-level `model_calls` 2 against accounting total 5 over 5 operation rows, verified by parsing that file in this session. The AD01 C4 table used the top-level counter while the ledger used the accounting union, so the column summed to 37 against the ledger 40. Fixed `reports/AUTONOMOUS-DEVELOPMENT-01.md` resume row Calls 2 to 5 with the definition stated beside the table, and added `count_definition` to `reports/workstreams/inv-a-c4-ledger.json` naming the unused top-level counter. Recomputed in this session. Report Calls column, ledger, and accounting union now all sum to 40. No other trace diverges.

## Verdicts without edits

INV-R-T11. Already resolved on this tip by `9f273ec`. Recomputed the per-operation settled token sum from committed bytes in this session. Total is 17383 exactly as the corrected lane D row states.

INV-E-02. Already resolved on this tip at `5ff0f1e`. The AD-06 row states 72 of 72 checker clean with retained-byte execution 45 of 72, matching the finding correction.

INV-E-03. Resolved as an explicit limitation, no edit. The EC02 cap reconciliation cites 26 gateway receipts totaling 48928 in and 41812 out with no receipt file under `evidence-live/` or `evidence-ad01/c4-live/`, verified by glob in this session. The bullet is qualified to the ledger and states no breach and no total external spend can be determined, with unknown liabilities open. Unreplayable numbers stay labeled, not filled.

## Verification

`python3 reviews/probes/inv_a_baseline_gaps.py` exits 0 with 17 pass and 0 fail after the edits in this session.
