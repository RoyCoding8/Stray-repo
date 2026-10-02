# Executable Coordination 02 — integration handback

Tip on `codex/implementation-executable-coordination-02`
(remote-equal, verified — see tail). Base `6d5f4f7` through
assessment `322c1e5`.

## Task graph and lane ownership

| Lane | Branch tip | Owned paths | Takeover |
|---|---|---|---|
| D | `994991c` | bounded historical source/report fixes | no — specialist delivered, merged with closure gate; F-EC02-D01 probe recorded (fails identically at base, kept) |
| R | `4a19366` (+`0ae9d4b` inspected) | controller, outcome/liability shape, pair identity | no — serial-merged after inspection |
| W | `7bd316b` | freeze, oracle, checker, corpus | yes — writer failed provider-side; coordinator finished inline, 17/17 green, merged as `d02e69a` |
| E-early | `25e2e3f` | trial schema, cost union, freeze assembly, promising rule, preflight | no — merged, 26 green |
| L | `e0b7378` | experience packet, doubled construction, strict gate, selection | no — ran after R/W interfaces landed, merged as `7e3dadc` |
| E-full | `905213b` | `experiments/coord02/entry.py`, evidence round trip | yes — writer failed provider-side; coordinator built inline, 31/31 green, merged as `ed00287` |

Serial merges, post-merge gates on the merge result (never
branch-local green alone). One add/add conflict
(`experiments/coord02/__init__.py`, union re-export); one stale-pin
fix (single `oracle_raw` read, W01).

## Interface decisions

- Pair identity `(freeze, panel, task, repeat, arm)` — R-owned,
  confirmed by all lanes.
- Trial version `coord02-trial/1`; cost-union with dedup-or-raise;
  freeze schedule canonical and exact (`verify_freeze` rejects scoped
  subsets by design — a subset freeze was attempted and deleted).
- Failed trials carry exactly the failed protected quotes
  (schema+checker joint contract; 0/0/0 placeholder deleted).
- All four arms share one controller path with lane L
  `dev_constructor` workers; `plan_children` is the single plan
  source (`single` S/A, `decompose` F). Doubled stand-ins labeled
  `doubled-dev`; entry `--label` defaults to it.
- Evidence restages the assembled candidate tree from team tables
  (launch snapshot + child outputs), re-grades with the oracle, and
  writes under the canonical freeze. `candidate_digest` keys the
  assembled tree bytes, never the procedure digest.

## Verification observed

Real PostgreSQL (`ec02test_d/r/w/l/e`) + real subprocesses, no model
calls. Post-merge on `ed00287`:

- `test_coord02_runtime` + `test_coord02_workload` +
  `test_coord02_learning`: 41 passed.
- `test_coord02_experiment`: 31 passed, including the doubled
  96-cell development round trip (12 tasks x 2 repeats x 4 arms)
  with checker-clean evidence and clean `status_view`.
- G1 structural probes green
  (`test_ec02_disconnect_and_substitution_fail_visibly`,
  refused-plan dispatch, binding checks).
- Fresh-checkout replay: clean clone + `uv venv` + `pip install -e .`
  imports the entry (`ARMS == ('S','A','F','L')`); no private scratch
  in the replay path (only `tempfile` staging inside the evidence
  root).

## Gate dispositions

- G0 contract and delivery: complete.
- G1 integrated mechanics: complete on doubled cells (authored
  controls labeled; disconnect/substitution probes catch at the
  controller entry).
- G2 live vertical path: NO-ACQUISITION FALLBACK (prescribed,
  design §11). Temporary local-gateway grant spent 24 construction
  calls (2 lineages x init+repair x 6 rounds, isolated evidence
  DBs, all provider-reported unbilled): 0 usable `entry`
  payloads — timeouts/empties at every deadline to 600s, while
  trivial prose probes answer in ~3s and any JSON-object prompt
  returns no text. Three root causes repaired and doubled-gated
  (prompt never stated the `entry` contract; fixed operation-id
  prefix collided across campaigns; raw canonical-JSON messages
  trigger provider no-text) — see
  `experiments/coord02/evidence-live/NO-ACQUISITION.md`. No
  authored bytes inserted into any live arm. Episode grant
  untouched (0/204).
- G3 frozen comparisons (96 evaluation + 48 transfer): BLOCKED on
  G2 — no package to freeze; 144 episodes against a known-empty
  arm would spend the grant for zero information.
- G4 validation and delivery: partial — verdicts/costs rederived
  from committed evidence on the doubled panel; live-DB receipt
  comparison stands on the construction receipts above;
  full-panel regression awaits G2/G3.

## Answerable now (doubled evidence)

Package execution works end to end through plan/admit/children/join
with real grading; coordination mechanics (partitions preserved,
child bytes executed, joins authoritative) are green. Correctness
benefit, efficiency benefit, scope transfer, and the section-13
decision table need live panels — null/negative results will be
reported as such, not marked complete while blocked.

## Detailed evidence

Lane reports: `reports/workstreams/ec02-D.md`, `ec02-R.md`,
`ec02-W.md`, `ec02-L.md`, `ec02-E.md`. Entry:
`experiments/coord02/entry.py`. Live fallback:
`experiments/coord02/evidence-live/NO-ACQUISITION.md`. Design:
`docs/design/EXECUTABLE-COORDINATION-02.md`.

## Procedural incident (coordinator-owned)

Doubled gate runs of `test_coord02_learning.py` TRUNCATE
`ec02test_l` per-fixture — the same DB early live rounds used.
Four rounds of live construction receipts were wiped; round
summaries survive in scratch logs only. Remaining live work moved
to isolated `ec02test_live`. Standing rule: live-evidence DBs must
never equal a test default (recorded in project memory).
