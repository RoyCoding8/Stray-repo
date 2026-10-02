# EC02 closure report (C1–C5 integration batch; live C2 executed, no acquisition, no comparison)

Branch `codex/implementation-executable-coordination-02`, integration lane
`repair/ec02-acquire-continuity`, this revision written at `ccbe25f`,
extending the `bfe1006` report with the granted live C2 execution (C5).
The prior unconditional closure label was not accepted on review
(`reviews/EC02-AD01-COMPLETION-ASSESSMENT.md`, EAR-01–06) and the BDF12D5
review's C1 PASS was not accepted either
(`reviews/EC02-AD01-BDF12D5-REVIEW.md`). This report supersedes the verdict
sections of the previous revision while preserving every as-run evidence
inventory: historical M3/M4 doubled batteries
(`reports/EC02-M3-ACQUISITION.md`, `reports/EC02-M4-FROZEN.md`), the live
`evidence-live/c2-acquisition6.json` export, and
`evidence-ad01/c3-trajectories/` remain committed and unchanged.

## What changed this batch (implementation, all deterministic)

- Protected-overlay guard migrated to the broker-backed child dispatch path
  (`cf817d2`): `oracle.overlay_files` is patched to raise around
  `dispatch_admitted_child`, proving the shared production child path never
  reads the protected overlay. The obsolete `arm_child_factory` test was
  deleted, net −13 lines.
- Grader-child containment leak closed (`dfc78af`): the grading child ran with
  `-I` only, which still processes host site-packages; the repository venv
  carries an editable-install `.pth` pointing at the repo `src`, so candidates
  could import repository code. The child now runs `-I -S` on the bare
  interpreter, and the isolation no longer depends on host site configuration.
  The failing test was the honest detector; the venv postdates the test.
- `select_candidate([])` no longer crashes (`b69c3b1`): empty construction
  results now return the same none-selection verdict as two invalid
  candidates. Reachable from the live driver when every response is unusable.
- Four stale test contracts migrated to the d2e3a78 accounting rules
  (`f3a1830`): ecr202's unknown-usage fixture (model-inference op, not
  sandbox), exec stop/unsupported per-proposal freeze identity (replayed
  settled receipts otherwise masked divergence), the experiment round-trip
  (doubled panels assert exactly the unknown-cost problem set and its
  reproduction through `status_view`), and the team-solver `acquire2` test
  (strict xfail; executed source unrecoverable per
  `reports/workstreams/ec02-D.md`).
- Grant enforcement (`666cc07`): `preflight_live` now compares the declared
  `EC02_LIVE_GRANT_CALLS` against construction demand and refuses below it;
  `construction_budget` carries `live_calls_authorized` bounded by the
  four-call study ceiling; the `ConstructionLedger` enforces the authorized
  count and reports `ceiling` plus `study_ceiling`; the live driver derives
  its budget from the admitted verdict's grant and refuses grants above the
  study ceiling. Allocation seeding sizes units by authorized calls.
- Construction prompt contract (`666cc07`): the response example and
  `required_response` now carry the `--selftest` guard that the profile
  check enforces. Root cause of both live profile failures on
  `ec02test_c2live6`: the emitted programs crashed indexing `sys.argv`
  under `python policy.py --selftest`, so capability verification failed and
  both lineages were rejected. The prompt previously demonstrated a program
  that could not pass its own gate.

## EAR dispositions

| ID | Disposition | Evidence |
|---|---|---|
| EAR-01 repair stand-in | Closed (deterministic) | Stamp channel deleted; recording doubles change submitted+graded bytes; comment-only bytes change digest only |
| EAR-02 fabricated accounting | Closed (deterministic) | `_cell_costs` reads measured usage via `costs_for_operations`; `write_evidence` unions from the store; unknown model spend stays unknown with an explicit liability |
| EAR-03 resume/authority | Closed (deterministic) | Durable campaign root bound before effects (`ConflictPayload` on change); construction allocations bound to one immutable attempt prefix (`4c6d2db`); recorded terminal policy decisions replay after settlement (`c2ab917`) |
| EAR-04 repair closure | Partial (deterministic + live) | `construct_lineages` repairs with a caller-supplied prior failure and the driver uses broker-backed `run_child_factory`. Live: 2 repair calls spent on `ec02test_c2live8`, both unusable (unparseable); the repair allocation is exhausted, not merely requested. Limitation: the committed driver (`evidence-live/c2-repair8.py`) feeds both lineages the lineage 1 stopped/probe-only failure text, so lineage 2 never received its own schema failure (`plan carries only action+shape+children`) as repair feedback |
| EAR-05 AD01 initiative | Closed (deterministic) | Accepted action governs dispatch; I/R differ at selection; stop stops; learner sees accumulated observations |
| EAR-06 persistence/budgets | Closed (deterministic) | Decisions persisted before effects; campaign schedules persisted with payload digests (`5451b8b`); diagnostics charge the trajectory query budget with aggregate caps enforced (`7a4f9eb`) |

The grant-enforcement remainder named in the review's EAR-02/03 line ("public
campaign/selection resume and grant enforcement remain required integration
work") is closed by `666cc07` plus the earlier resume commits: campaign
resume replays through journal-keyed steps (`8ab1c72`), and live spend is
refused below the declared grant before any operation is ensured.

## Live campaign (C2, executed on granted authority, no acquisition, no comparison)

- Authority: `EC02_LIVE_GRANT_EPISODES=48`, `EC02_LIVE_GRANT_CALLS=4` on
  `ec02test_c2live8`. Spent 4/4, selection `none`. Evidence
  `evidence-live/c2-acquisition8.json` plus the repair round
  `evidence-live/c2-acquisition8-repair.json` (repair transport reroutes
  through `experience.py`, not the coordinator script path). Per-attempt
  reconciliation across `c2live6`/`c2live7`/`c2live8` is in
  `reports/workstreams/inv-a-c2-ledger.json`; no grant document exists in-repo.
- Lineage-specific init outcomes (not identical): lineage 1 parses and
  profiles clean, then every development task ends stopped with reason
  "acquisition probe only" (the candidate probes once, never proposes a
  plan, solves nothing), so `execution_admitted` is false and
  `valid_execution` is false. Lineage 2 parses and profiles clean, then
  every development task ends policy-invalid with reason "plan carries
  only action+shape+children" (a schema failure, not a probe-only stop).
  Selector `coord02-dev-select/1` ranks [1, 2] on valid-execution first:
  neither candidate is executable under the contract.
- Repairs: 2 calls, both `repair_kept_usable: false` with
  `repair_parsed_ok: false`. The grant is exhausted with full receipts;
  no further live construction is authorized.
- Fabrication closure (deterministic, proven live-adjacent): the pass-1
  settlement resweep refuses launcher receipts for never-dispatched
  operations and requires dispatch generation on redispatch; the
  pass-3 grant merge gates live spend on grant capability (not key
  presence) while exempting labeled/recording doubles, so deterministic
  tests stay grant-free and live paths stay gated. Both behaviors are
  pinned by regression tests (`test_p3g_grant`, `test_p3g_final`,
  `test_p3gf_grantfix`, `test_coord02_state` ECA union suite).
- Cap reconciliation (qualified, see `reports/workstreams/inv-a-c2-ledger.json`):
  design ceiling ≤48 dev episodes incl. calibration and validation;
  committed fallback export holds 96 dev cells; 26 gw receipts (48,928
  in / 41,812 out). The per-attempt granted roots are `c2live6`: 204
  episodes + 4 calls (self-reported in its export), `c2live7`: 48 + 4
  (admitted in its run log, crashed before settlement), `c2live8`: 48 +
  4 (admitted in both run logs, ledger 4/4 spent, 0 refused). No
  cross-database aggregate of authorized vs consumed vs reserved spend
  exists in-repo and no grant document exists in-repo, so no breach and
  no total external spend can be determined here; unknown liabilities
  (gateway-side usage, the crashed attempt, the remote 16-receipt
  anchor) stay open in the ledger. No new tags/roots/DBs reset
  consumed authority.
- REQUEST: none outstanding. The repair half of the ceiling was granted
  and spent. A new grant would be a new study, not a remainder.

## Final integrated tests (merged tip `ccbe25f`)

Serial full suite on disposable DBs only (`ec02test_*`; `ec02test_live`
receipts still 16, untouched), clean probe DB, no ignores:

```
pytest tests/ -q -p no:cacheprovider
```

1329 passed, 1 xfailed in 3453.30 s. The xfail is the unrecoverable
`acquire2` import. Fifteen merges landed without a full run mid-batch and
the gate caught 35 failures in four root clusters, all fixed and re-gated:
slop-trimmed frozen import (1-line revert), construction live-gate double
exemption (mirrored across both predicates), ECA helper brought onto the
ensure→dispatch→receipt flow, and the representation composition pin
rebound from name-equality to byte-binding with a per-slot execution
namespace. The stale `settlement_restore_probe` that masked the restore
suite as red was dropped and recreated; environmental, not a code defect.

## Verdict

**C1 substantial integrated implementation (deterministic, fully gated)
with material information/resource gaps per
`reviews/EC02-AD01-84D2094-ASSESSMENT.md` IR-01/IR-03; C2 executed on
granted authority with 4/4 construction calls spent, selection none,
lineage 1 probe-only stops and lineage 2 schema failures, both repairs
unusable. No learned-policy panels were run** (running them without a
candidate is the fabrication this contract forbids), so no benefit
comparison occurred and no learned-policy negative is claimed. Provenance
is limited to accounting summaries: the four raw construction responses
and their full receipt/input linkage were never exported
(`reports/workstreams/inv-a-c2-ledger.json` G1/G2). Live spend accounting beyond
the declared per-attempt grants cannot be reconciled from committed
evidence; no breach and no total external spend is determined here.
