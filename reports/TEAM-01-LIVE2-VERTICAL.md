# Team 01 live repair — vertical path (CB2-01 completion)

Assignment `WORKER-COGNITIVE-BATCH-02-LIVE-COMPLETION.md`, vertical-path
stage only. Panels are **not** rerun here. Code: `experiments/team01/
solver.py|pubcheck.py|run_live2.py`, lane merged as `322b11e`; evidence
bundle `experiments/team01/evidence-live2-vertical/`; prior hybrid
evidence recovered as labeled diagnostic in
`experiments/team01/evidence-hybrid/` (`a4a1fdb`).

## Proven: one actual live S/P/T repair path (`team01-t01`)

Same model/config/task/source/tool access per arm
(`muse-spark-1.3-contributor-free`, responses API, low effort, bounded
per-episode allocations). Final live run (DB `vpath_live3`):

| Episode | Outcome | Protected |
|---|---|---|
| S (iterate + tool feedback + self-review) | success | 6/6 |
| P (2 independent attempts, join selects) | success, selected-w1 | 6/6 |
| T (model chose decompose, per-node ctors) | success | 6/6 |
| substitution (valid-but-wrong injected) | failure, r1 join rejected | 0/6 |
| disconnect (w1 output dropped) | refused, no freeze | — |
| incompatible (authored renamed entry, labeled) | failure after 1 rework repair round | 0/6 |

Traceability: constructor op → gateway receipt → response bytes digest ==
submitted digest (independent reviewer re-verified on the S episode,
4/4 PASS, exact digests); prompts carry no family/kind labels; scored
trees assemble from submitted bytes only (`_final_tree_live`; no
`prepare_tree`/`_tree_files` in the solver path). Join-attempt history
(r1/r2 check ops, codes, details) is recorded per episode.

## Bugs found and fixed (with failing-before evidence)

1. **Alternatives coverage** (apparatus, mine): candidates must cover the
   whole snapshot; P refused with `MISSING_EVIDENCE`. Fix: whole-tree
   ownership for P + semantic spec-echo check (a byte-exact rule had
   refused good repairs over a trailing newline — verified byte-level).
2. **Revise carrying vs rework** (shared `team.py`, pre-existing): revise
   carried r1 submissions (attempt completed, old bytes copied), so any
   repair round died at re-dispatch (`attempt … is completed`). Fix:
   `revise_team_plan(rework=[…])` mints fresh attempts; unknown nodes
   rejected. Before: `SettlementError: child w1 never observed`; after:
   repair round dispatches, submits, rejoins (proven live, r2 check ran).
   Existing `test_team_runtime.py` green (no default-behavior change).
3. **Stale-receipt reuse on rerun** (test hygiene + real hazard): fixed op
   ids + fixed per-episode allocations silently reused old responses and
   drained grants across reruns. Fix: op nonce per episode, unique test
   tags; same-DB reruns now fail loud (duplicate seed) instead of stale.

## Verification boundaries

Actual: live gateway calls with receipts/usage; real broker dispatch,
submit, join, freeze, revise; costed public-case tool runs through
sandbox ops. Doubled: scripted-gateway gates (10 passed, incl.
spec-rewrite rejection and data-flow-only-submitted-bytes). External:
provider billing. Model flakiness observed as costed classes
(empty-output repair call, byte-identical P attempts) — counted, not
hidden. Focused gates on the merged tree: 67 passed, 0 failed
(solver/runtime/world/experiment/live/checkpoint/restore).

## Not done (next stages per the assignment)

Acquisition/transfer via broker-routed inference, template-candidate
behavior validation, full live comparison under a new freeze, new
acceptance checks, full-suite rerun after changes settle, push. The
frozen `build-1-bind-first` template and hybrid verdicts stay historical.
