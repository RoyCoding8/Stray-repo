# RPR-01 inventory: supplied vs constructed

Machine-readable form: `inventory.json`. Frozen fixture panel:
`fixtures/` (`manifest.json` + `manifest.sha256`, version `RPR-01/1`).

## Supplied to all arms (this lane)

- Task syntax and legal deletion/subgraph rules (`software.py`, `graphs.py`).
- Reference interpreter plus both faulty interpreters, stale-read-after-overwrite
  and stale-state-after-clear (`software.py`).
- Designated-observation witness spec and oracle query access with the
  `preserved | not_preserved | invalid | unknown` vocabulary (`checkers.py`).
- Separately written references: transition-table interpreter
  (`software_reference.py`); exhaustive 2-coloring and explicit triples
  (`graph_reference.py`).
- Baseline reducers: ddmin-style deletion and domain-aware greedy (`reducers.py`).
- Fixed-seed split generators plus the frozen 44-task fixture panel with a
  content-verified manifest (`splits.py`, `fixtures/`).
- Four scope/validity controls and the mixed subsequent-use panel (`splits.py`).

## Constructed later (NOT supplied; Lane D owns)

Arm lessons/procedures, shared core and adapters, frozen selectors,
dispositions and the A/B/C comparison evidence.

## Splits and seeds

Software 1101/1201/1301 and graphs 2101/2201/2301 for
development/check/evaluation (6/4/8 per family); controls 3101; use panel
4101. Task `i` of a split derives deterministically from its split seed.

## Holdout and overlap

Held out of development: odd-cycle length C9, the shared-edge double-cycle
pattern, the joined-by-path double-cycle pattern and all use-panel seeds.
Single-cycle+tree and distractor patterns recur across splits with held-out
seeds, and C5/C7 recur inside evaluation combos. This is finite-family
transfer, not broad out-of-distribution generalization.

## Graph-invisibility barrier

`fixtures/software/**` carries no graph vocabulary
(vertices/edges/bipartite/triangle/cycle); enforced by
`test_graph_family_invisible_to_source_side`. Source acquisition sees the
software directories only.
