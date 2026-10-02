# Workstream cb01-source: RPR-01 source instruments (Lane B)

Branch: `codex/cb01-source` from `0b323b7`. Owned paths only:
`experiments/representation/**`, `tests/test_rpr01_*.py`,
`reports/workstreams/cb01-source.md`. No shared-contract edits.

## What was built

- Software family (`software.py`): deterministic key/value machine with
  `set/get/clear/del`, reference interpreter plus two faults
  (stale-read-after-overwrite, stale-state-after-clear), distractors,
  multi-key tasks, stable get-observation ids with a typed
  present/missing value-disagreement witness. Tasks are JSON data, max 24 ops.
- Graph family (`graphs.py`): triangle-free non-bipartite simple undirected
  graphs, C5/C7/C9 cycles, attached trees, disconnected distractors,
  shared-vertex/shared-edge/bridged double cycles. Legal outputs are
  id-preserving subgraphs, max 10 vertices / 18 edges.
- Independent checkers (`checkers.py`) with `preserved | not_preserved |
  invalid | unknown` vocabulary, checked measure and bounded reasons, plus
  budgeted oracles (default 16 queries, over-budget yields `unknown`).
- Separately written references (`software_reference.py` transition table;
  `graph_reference.py` exhaustive 2-coloring and explicit triples) sharing
  no code with the primaries.
- Baseline reducers (`reducers.py`): deletion-only ddmin and domain-aware
  greedy over abstract atoms; trials that cannot parse are skipped before
  querying, only `preserved` trials are accepted.
- Splits (`splits.py` + `fixtures/`): fixed-seed 6/4/8 development/check/
  evaluation per family, 4 scope/validity controls, 4-case subsequent-use
  panel, content-verified manifest (`manifest.json` + `manifest.sha256`,
  version `RPR-01/1`). Supplied-vs-constructed inventory in
  `inventory.json` / `INVENTORY.md`.
- Graph-invisibility barrier: `fixtures/software/**` carries no graph
  vocabulary; enforced by test.

Reuse: `settlement.common.payload_digest` for task identity and
`ResultCode`-shaped checker vocabulary. Broker/allocations/artifact
publication have no meaning for offline data instruments; they belong to
Lanes C/D, which consume these fixtures through the recorded inventory.

## Verification

Command (real PostgreSQL 16, host-param DSN):

`SETTLEMENT_TEST_DSN='postgresql://ubuntu@/settlement_cb01src?host=/var/run/postgresql' .venv/bin/python -m pytest tests/test_rpr01_software.py tests/test_rpr01_graphs.py tests/test_rpr01_checkers.py tests/test_rpr01_reducers.py tests/test_rpr01_splits.py tests/test_rpr01_db.py -q`

Result: 46 passed. Coverage per file: software 8, graphs 6, checkers 8
(including exhaustive interpreter agreement on 399 small sequences x3
runners and BFS-vs-exhaustive plus triangles-vs-triples agreement on all
1099 graphs up to 5 vertices), reducers 12, splits 11, db 1.

## Fidelity-control evidence (observed)

| Probe | Observed |
|---|---|
| 36 benefit tasks valid, within caps | all `task_is_valid` / `witness_holds` true |
| `ctrl-sw-wrong-obs` | `invalid / invalid-task`, reducer `initial-not-preserved` |
| `ctrl-sw-invalid` | `invalid / invalid-task` |
| `ctrl-gr-triangle` | `invalid / invalid-task` |
| `ctrl-gr-bipartite` | `invalid / invalid-task` |
| smaller + wrong witness (sw) | `not_preserved / witness-lost-agree` |
| smaller + bipartite subgraph (gr) | `not_preserved / witness-lost-bipartite` |
| forged ops / new vertex / task swap | `invalid / illegal-deletion`, `illegal-subgraph`, `task-mismatch` |
| incumbent | `preserved / ok-incumbent`, u = 0 basis |
| oracle past 16 queries | `unknown / budget-exhausted` |
| reducer sample sw-dev-00 (15 ops) | ddmin 15 -> 3 (10 queries), greedy 15 -> 3 (19 queries), both `preserved` |
| reducer sample gr-dev-00 (12) | ddmin 12 -> 11 (32 queries), greedy 12 -> 10 (23 queries), both `preserved` |
| use panel | 2 supported valid, 2 out-of-scope refused |
| manifest tamper (1 byte) | `verify_manifest` reports mismatch |
| software fixtures graph scan | zero hits for vert/edge/bipart/triangle/cycle/graph |

Nondecreasing-measure note: a legal subobject of equal measure is
byte-identical to the incumbent (subsequence/subset with equal size), so
the only accepted equal-measure case is `ok-incumbent`. Forged
supersets are rejected as `illegal-deletion`/`illegal-subgraph`. No
separate reason code was kept; both measures ride in every report for
Lane D's `u` computation. Triangle-loss on legal candidates is likewise
impossible (subgraphs of triangle-free tasks), so candidate-side
checking is validity, then legality, then bipartiteness; triangle
detection is covered by unit, reference and control evidence.

## Contract change requests (coordinator decides; none applied)

1. J2 wording: confirm the Lane B reading that the graph witness needs no
   per-task observation id (identity is the task plus the three-way
   conjunction), and that equal-measure acceptance is limited to the
   byte-identical incumbent with no dedicated reason code.
2. No new migration or shared-module change is requested by this lane.

No live model calls were made; no credentials exist in this lane.
Graph content was never placed in source-side fixtures.
