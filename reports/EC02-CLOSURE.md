# EC02 closure report (behavioral batch; live C2 remainder blocked)

Branch `codex/implementation-executable-coordination-02`. The prior
unconditional closure label was not accepted on review
(`reviews/EC02-AD01-COMPLETION-ASSESSMENT.md`, EAR-01–06); this report
supersedes `reports/EC02-CLOSURE.md`'s verdict section while preserving
its evidence inventory. Historical M3/M4 doubled batteries remain fixture
evidence in `reports/EC02-M3-ACQUISITION.md` / `reports/EC02-M4-FROZEN.md`.

## What changed this batch (C1, gated)

- Shared admitted child path (B-EXEC): `dispatch_admitted_child` renders
  the admitted obligation + observations + current bytes, dispatches ONE
  broker `MODEL_INFERENCE` call on the configured child model, parses the
  `{files, notes}` response and returns model bytes. `run_cell` routes
  S/A/F/L through it after admission. The stamp channel
  (`admitted_child_factory` + hash-comment append) and the FIXTURE-only
  `arm_child_factory` gate are DELETED. A reads the actual retained
  source; F runs the frozen conditional on probe evidence; L invokes the
  exact retained bytes; stop/refusal dispatches zero dependent work.
- Store-derived costs (B-AUTH): `costs_for_operations(dsn, op_ids)` unions
  measured receipt usage (shared op once, unknown raises); `_full_usage`
  extracted behavior-preserving. `run_cell` rewiring is tracked, not done.
- Operative AD01 dispatch (B-INIT) and outside-menu retention (B-ACQ):
  accepted action selects the dispatched task; refusal/stop close dispatch;
  `run_use` executes retained member bytes directly.
- Independent gate (B-VERIF + follow-up): public-path lock test;
  7 stale-shape tests updated to the post-stamp contract with per-test
  justification; old characterization probe file byte-frozen, never
  inverted. C1 PASS: 42-test core + 90-test neighbors + 4 DB-backed green.

## EAR dispositions

| ID | Disposition | Evidence |
|---|---|---|
| EAR-01 repair stand-in | Closed (deterministic) | Stamp channel deleted; recording doubles change submitted+graded bytes; comment-only bytes change digest only |
| EAR-02 fabricated accounting | Partially closed | Store-derived union helper green; `run_cell`/`write_evidence` rewiring remains |
| EAR-03 resume/authority | Partially closed | Claimed-op validation kept; durable campaign root + eligible-repair acquisition remain |
| EAR-04 repair closure | Open, blocked | 2 live inits, 0 repairs on the ledger; repair allocation requested, not granted |
| EAR-05 AD01 initiative | Closed (deterministic) | Accepted action governs dispatch; I/R differ at selection; stop stops |
| EAR-06 persistence/budgets | Partially closed | Decision+pending persisted; per-action budgets threaded; full cap sheet pending |

## Live campaign (C2, blocked remainder)

- Authority: 2 live construction inits on `ec02test_c2live6`, 0 repairs;
  `selection: none` stands as a narrow observation, NOT a closed study.
- Cap reconciliation: design ceiling ≤48 dev episodes incl. calibration
  and validation; committed fallback export holds 96 dev cells; receipts
  show 26 gw receipts (48,928 in / 41,812 out). Recorded as a discrepancy
  (no redacted grant document exists in-repo); no new tags/roots/DBs reset
  consumed authority.
- REQUEST (single, per §2): 2 repair construction calls (unspent repair
  half of the ceiling, same model/endpoint) + revalidation-episode cover.
  No new lineages, roots, or eval/transfer panels.

## Verdict

**C1 complete (deterministic); C2 blocked-remainder preserved exactly.**
No learned-policy panels were run (no candidate exists — running them
would be the fabrication this contract forbids). Live C2/C4 run
automatically when their allocations arrive.
