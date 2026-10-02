# EC02-D workstream report: Team 01 historical delivery closure (G0)

Base: `e9edbea` (G0 contract baseline)
Integration tip merged additively first: `d9795b6`
  (`origin/codex/implementation-executable-coordination-02`)
Merge commit: `be87bdd`
Product commit: `e4221a7` (derived corrections, closure tests, report links)
Branch: `ec02-lane-D` (worktree `/tmp/asv2-ec02/.worktrees/lane-D`)

No live panels were rerun, no template result was forced, no model calls
were made. All analysis below is offline over the committed raw bundle.

## Recovery provenance: acquire2.py / reconcile2.py — UNRECOVERABLE

Searched, read-only, without modifying the retained checkouts:

- `git log --all -- experiments/team01/acquire2.py
  experiments/team01/reconcile2.py` in this repo: no commit ever contained
  either file.
- `/tmp/asv2-batch02` (`codex/implementation-cognitive-batch-02`,
  `5864740`) and `/tmp/asv2-batch02/.worktrees/live2` (`wt/live2`,
  `a36741f`): both working trees clean, no untracked scratch; neither file
  present. Case-insensitive filesystem search over both trees finds only two
  orphaned bytecode files in the live2 tree:
  `experiments/team01/__pycache__/acquire2.cpython-312.pyc` (13378 bytes,
  Sep 12 21:48) and `.../reconcile2.cpython-312.pyc` (7249 bytes,
  Sep 12 22:34).
- The bytecode was not decoded, decompiled, or executed: decompilation
  cannot yield byte-exact source and must never be presented as the
  historical implementation.

Result: byte-exact executed source is **unrecoverable**. Nothing is
committed under those module names and no reconstruction is offered as
historical. Partial API knowledge survives in `tests/test_team_solver.py`
(`acquire2.build_template(live_db, gateway, allocation_id, tag,
dev_records, evidence_root, attempt)` returning `directive` / `error` /
`digest`), which constrains but does not recover the modules.

## Corrected verdicts (raw records and historical verdict bytes untouched)

Derived views, linked both ways to the raw bundle:

- `experiments/team01/evidence-live2-panels/derived-correction-live2.json`
- `experiments/team01/evidence-live2-panels/derived-totals-live2.json`

Generator (tracked, offline): `experiments/team01/closure2.py`.
Regression: `experiments/team01/test_closure.py` (10 tests).

Refusal accounting: `live2-S-team01-t06-r2` is a complete refusal with all
receipts present and allocation balance 64125 ≥ 0. The record's 0/0 usage
predates the refused-usage fix; the receipt-derived 890 in / 563 out is
used and the cell counts as zero success (`solved=false`). The mismatch is
a record-writing defect with settled effect, not an unsettled external
effect and not missing evidence.

Three-way distinction per cell (`classify_cell`): empirical outcome
(`success` / `failure` / `refused` → solved True / False / False),
evidence availability (`available` vs `unavailable-evidence` for missing
records or missing receipts), effect settlement (`settled` vs
`unsettled-effect` for missing receipts or failed allocation). Accounting
agreement is reported separately from all three.

Corrected rules (via the existing `checker.finite_panel_rule` on
adjusted copies; refused input mapped to zero-success with receipt usage):

- eval: `complete-records` TRUE (was FALSE), `beats-S` still FALSE
  (28 tools vs 19, ratio 1.47 > 1.25), `beats-P` TRUE, S tokens
  93942 → 95395 (+890/+563), S solves stay 15. Reasons now `beats-S`
  alone. Decision unchanged: not promising.
- transfer: unchanged (complete, both beat clauses FALSE). Not promising.

Calibration-vs-probe correction: stored dev calibration (probe None) is
9 success + 3 failure, not the reported 10 + 2. t09 S+T pass protected 6/6
but are join-rejected; t09 P fails protected 0/6 (and join). Probes are
separate: `template-validation` 1 success, `continuity` 1 success.
14 dev-tagged = 11 success + 3 failure. `reports/TEAM-01-LIVE2-PANELS.md`
table row corrected in place; a closure pointer section links the derived
files.

Operation-identity-union totals: episode-only 211 model / 135 tool /
174881 in / 255342 out (recomputed from records; matches ledger and
reconciliation top level). Construction `live2-build-1-477ccb95` adds
1 model call, 1490/1523 tokens, op identity disjoint from all episode ops.
Whole campaign: 212 model / 135 tool / 176371 in / 256865 out.
Episode-only vs whole-campaign are now stated separately; the report's
single "campaign model calls 211" figure is the episode-only union. No
pre-ledger campaign-chargeable calls exist in the committed bundle;
in-episode retries sit inside episode usage; anything earlier is quoted
unavailable, not estimated.

Template label: `coordination-template/2` (digest `e14149f5…`, 1386 chars)
is model-generated advisory text appended to planner prompts
(`solver.py:plan_prompt`) and warm-T constructor context; `applies_when`
appears in JSON only and is enforced nowhere in code. Executable
coordination-template acquisition remains open; the treatment confounds
coordination advice with task-solving hints.

## Fresh-checkout command (verified byte-identical)

Detached checkout `git worktree add --detach /tmp/ec02-D-verify e4221a7`,
all five lane files confirmed tracked, derived files deleted and
regenerated from tracked raw bundle only (`diff` clean), then:

    python -m experiments.team01.closure2 --evidence experiments/team01/evidence-live2-panels
    pytest experiments/team01/test_closure.py -q    # 10 passed

Checkout removed after verification.

## Modified paths

- `experiments/team01/closure2.py` (new derived-correction generator)
- `experiments/team01/test_closure.py` (new, 10 regression tests)
- `experiments/team01/evidence-live2-panels/derived-correction-live2.json`
  (new) and `derived-totals-live2.json` (new)
- `reports/TEAM-01-LIVE2-PANELS.md` (calibration row fix + closure section;
  historical evidence bytes untouched)
- `reports/workstreams/ec02-D.md` (this report)

Untouched per lane bounds: `src/settlement/*`, `migrations/*`,
`experiments/coord02/*`, `tests/test_coord02_*.py`, other lanes' paths.
`uv.lock` unmodified.

## Check outcomes

- `pytest experiments/team01/test_closure.py -q`: **10 passed**.
- Fresh-checkout reproduce: derived files byte-identical, tests 10 passed.
- No live calls attempted (no `TEAM01_LIVE_API_KEY` in this env; no other
  key spent). No DB used; no 43-minute suite (doc/script-only changes;
  no existing code path modified).

## Limits and follow-ups (for coordinator)

- `acquire2.py` / `reconcile2.py` remain undelivered; reproducibility of the
  acquisition path itself is still open worker-side history.
- CB2/LIVE disposition and roadmap updates beyond the bounded report links
  above belong to the coordinator/shared reports and were not made here.
- `pytest` default `testpaths` is `tests/`, so the closure tests run only
  by explicit path (as commanded above).
