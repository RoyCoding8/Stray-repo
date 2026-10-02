# Team 01 live2 — full panels (CB2 completion)

Assignment `WORKER-COGNITIVE-BATCH-02-LIVE-COMPLETION.md`, post-vertical
stages. Code: `experiments/team01/solver.py|checker.py|run_live2.py|
acquire2.py|reconcile2.py`; evidence bundle
`experiments/team01/evidence-live2-panels/` (86 episode records +
builds, ledger, frozen template, verdict, replay, reconciliation,
check-all review). Gateway `http://localhost:6446/v1`, API `responses`,
model `muse-spark-1.3-contributor-free`, low effort, per-episode bounded
allocations with nonces. DB `live2camp` (campaign) / `live2test` (gates).

## Campaign totals (all live)

| Phase | Episodes | Result |
|---|---|---|
| dev calibration (t01,t05,t09,t13 × S,P,T) | 12 | 9 success, 3 failure (t09 S+T protected 6/6 but join-rejected; t09 P protected 0/6) — corrected by lane D, see closure section |
| warm-T template-validation trial (t05) | 1 | success 6/6 |
| template acquisition | 1 build | directive, 1386 chars, digest `e14149f5…` |
| freeze | 1 | `live2-build-1` (single attempt, no fallback) |
| eval panel (8 tasks × T,S,P × r1,r2) | 48 | 47 success, 1 refused (t06 S r2) |
| transfer panel (4 tasks × warm-T,cold-T,S × r1,r2) | 24 | 24 success |
| continuity suspend/resume (t05 S) | 1 | suspended → resumed True, join True, 6/6 |

Spend vs declared envelope: dev 13/24 (12 + trial), builds 1/2, eval
48/48, transfer 24/24, probes 2/2. Campaign model calls 211, tool calls
135, tokens 174881 in / 255342 out. No cap breached, no overrun
(every reconciled allocation balance ≥ 0).

## Panel verdicts (`finite_panel_rule`, controls pass, ceilings hold)

- eval: T 16/16 vs S 15/16 (+1 refused) vs P 16/16. `beats-S` FALSE —
  T solved one more cell but used 28 tools vs S 19 (ratio 1.47 > 1.25).
  `beats-P` TRUE on the level rule (tie 16–16, fewer tokens and tools).
  `complete-records` FALSE (refused cell has no solved verdict).
- transfer: warm-T 8/8 vs cold-T 8/8 vs S 8/8. Both beat clauses FALSE
  (ties; warm-T used more tokens than cold-T, more tools than S).
  `complete-records` TRUE.

Neither panel is `promising`. The directive changed team decisions
(warm-T solved all transfer cells, including t09-family tasks) but
bought no efficiency beat within the 1.25 ratio. Valid negatives,
reported as such — no positive learning result manufactured.

## Honest negatives kept in evidence

1. t09 S+T (dev): model trees passed protected 6/6 standalone, but the
   broker join check rejected them at r1 AND r2 (`OBSERVED_FAILURE`).
   The join gate is stricter than standalone protected eval here; both
   cells are `failure`, quoted in `check-all-live2.json`
   (`unquoted-failure` flags are the checker correctly noting the
   failures are join-quoted, not protected-quoted).
2. t06 S r2 (eval): constructor produced no submittable artifact for
   w1 → `refused`, no freeze. Record kept; its usage block predates the
   refused-usage fix (0/0 vs receipts 890/563) and is retained as-run.
3. Reconciliation: 85/86 agree, zero missing receipts. The single
   unresolved cell is the t06 refusal above (usage-record mismatch, all
   receipts present, allocation OK).

## Bugs found and fixed during panels (with tests)

1. **Refused records under-reported usage** (mine): `_refused_record`
   hardcoded usage/costs zeros while gateway receipts showed real
   spend — found by `reconcile_campaign`. Fix: sum trace op usage.
   Test: `test_disconnect_refuses_without_artifact` asserts refused
   usage/costs equal the scripted call usage.
2. **`failure_quotes` crashed on multi-panel roots** (apparatus, mine
   to fix): `sorted()` over mixed None/int rep keys raised TypeError.
   Fix: `sorted(..., key=repr)`.
3. **`replay_panel` could not read live records** (apparatus gap):
   crashed on list-shaped receipts (`AttributeError`), `int(None)`
   revision (`TypeError`), missing join blocks (`KeyError`/
   `UnboundLocalError`), and mixed-type tail sort. Fix: accept flat
   receipt-identity lists (each verified against the receipts table),
   report `unbound-revision` as a mismatch, skip non-episode
   `continuity` probe records, `key=repr` tail sort. Test:
   `test_replay_accepts_live_record_shapes`.
4. **Join schema checks applied to resume records** (apparatus scope):
   `_check_record` demanded join blocks from `continuity` suspend/
   resume records, which carry none by design. Fix: scope the join
   checks to non-continuity records; resume verification stays the
   phase1/phase2 shape plus ledger entry.

## Independent reviews

- `check_all` over the committed bundle + live DB: 86 records,
  controls oracle+barrier pass, 7 problems — all quoted above, none
  hidden. Artifact: `evidence-live2-panels/check-all-live2.json`.
- `replay_panel` re-read every record against `live2camp` plans, joins,
  submissions and receipts: 1 mismatch (the refused cell). Artifact:
  `evidence-live2-panels/replay-live2.json`.
- `reconcile_campaign`: per-op receipt presence, receipt↔record usage
  equality, allocation balances: 85/86 agree. Artifact:
  `evidence-live2-panels/reconciliation-live2.json`.

## Delivery closure (lane D, EC02-G0)

Source recovery: `experiments/team01/acquire2.py` and `reconcile2.py` were
never committed on any branch and are absent from both retained checkouts;
only orphaned `__pycache__` bytecode remains, which cannot yield byte-exact
source and was not decoded. Recovery: **unrecoverable** — no reconstruction
is presented as historical. Full provenance in
`reports/workstreams/ec02-D.md`.

Derived corrections (raw records preserved; historical verdict bytes
untouched): `evidence-live2-panels/derived-correction-live2.json` (t06 S r2
refusal counted as zero success with receipt-derived 890/563 usage;
refusal vs unavailable-evidence vs unsettled-effect distinction; corrected
panel rules; `coordination-template/2` labeled advisory text with
unenforced `applies_when` prose) and
`evidence-live2-panels/derived-totals-live2.json` (calibration 9 success +
3 failure; episode-only vs whole-campaign operation-union totals).
Reproduce offline from tracked files only:

    python -m experiments.team01.closure2 --evidence experiments/team01/evidence-live2-panels
    pytest experiments/team01/test_closure.py -q

Corrected verdicts: eval `complete-records` TRUE, `beats-S` still FALSE
(reasons now `beats-S` alone), `beats-P` TRUE; transfer unchanged; neither
panel promising. No live panels were rerun and no template result was
forced.

## Boundaries

Provider-side billing unknown (free tier); internal consumption fully
counted. Scripted-gateway gates prove mechanism, not liveness;
liveness is proven by the 86 live episodes above. The frozen
`build-1-bind-first` template and hybrid verdicts stay historical and
are not mixed into these panels.

## Assessment finding dispositions (CB2-01–03)

- CB2-01 (arm-specific authored outcomes): CLOSED. Every S/P/T repair
  in this campaign ran through live model calls (211 calls, one
  gateway receipt per constructor op, nonzero comparator tokens:
  eval S 93942, P 73653). The solver path has no reference overlays:
  scored trees assemble from submitted bytes only, prompts carry no
  family/kind labels, P owns the whole tree, and the spec-echo check
  is semantic. Substitution/disconnect/incompatible diagnostic
  controls behave (vertical proof retained).
- CB2-02 (authored menu + nonempty fallback): CLOSED. `acquire2`
  contains no `BUILDS` menu: build-1 is model-generated directive text
  (1386 chars) from 9 actual dev records, validated by a warm-T trial
  (6/6), frozen as `live2-build-1` on the first of two allowed
  attempts. The explicit `none` path (`no build trial executed
  end-to-end`) was preserved and not taken.
- CB2-03 (campaign evidence absent from the tree): CLOSED. Hybrid
  evidence stays labeled diagnostic (`evidence-hybrid/`, `a4a1fdb`);
  the live2 campaign is committed as
  `experiments/team01/evidence-live2-panels/` (86 episode records,
  builds, ledger, frozen template, verdict, replay, reconciliation,
  check-all review). Fresh-checkout verification: a clean clone of
  `wt/live2` recomputes 86 records, controls oracle+barrier pass, same
  6 schema problems and same panel reasons — no provider, no DB. DB
  receipt verification remains a separately labeled additional check
  (`replay-live2.json`, `reconciliation-live2.json`).
