# Representation 01 — acquisition and transfer pilot report

Branch `codex/implementation-cognitive-batch-01`. Lane material by
Lanes B (source), C (execution) and D (acquisition); coordinator
verified digests, replay, and tests on the merged source before
publishing. Design: `docs/design/REPRESENTATION-01-IMPLEMENTATION.md`.
Shared contracts J1-J5: `reports/PLAN.md`.

## 1. Inventory: supplied versus constructed (RPR-01)

Supplied by Lane B (manifest `RPR-01/1`, digest
`54ae7c4a...`): software/graph task syntax with legal deletion and
subgraph rules, reference plus both faulty interpreters, the
designated-observation witness specifications, budgeted oracle access
with the `preserved | not_preserved | invalid | unknown` vocabulary,
separately written reference implementations, ddmin and domain-aware
greedy reducers, fixed-seed 6/4/8 split generators with frozen fixtures,
four scope/validity controls, and the four-case subsequent-use panel.
Supplied by Lane C (profile `representation-01/1`): the package and
composition envelope, the encode/start/advance/decode JSON schemas, the
real-execution runner with independent checking and per-task budgets,
and durable step receipts with resume.

Constructed by Lane D (this work): two acquisition contexts (6 software
development + 4 graph development tasks with parent refs, full baseline
transcripts, authored lessons), the shared atom core with its software
and graph adapters plus a no-search core for attribution, frozen arm
selectors derived from development transcripts only, the `RPR-ACQ/1`
freeze manifest with deterministic checker bundles, two trial protocols
with assignments and outcomes, 45 evidence records, the strict checker,
and the replay CLI. The live model campaign is not constructed: no
gateway is configured, and the exact blocker is recorded instead. No
model output of any kind appears in this study; every constructed
behavioral byte is labeled an authored fixture.

## 2. Apparatus (RPR-02/05/07 as consumed)

Compositions pair a domain-blind atom core (coarse feedback-driven
halving over anonymous atom indices, explicit tunables `chunk_frac`,
`max_proposals`, `order`) with one family adapter that translates tasks
to atoms and kept atoms back to source objects. Declared auxiliary
material carries the source snapshot; the core never sees raw tasks.
Every component invocation and every witness query is a real broker
operation with real receipts through `LocalLauncher`; the trusted
checker is a single-file bundle rebuilt deterministically from Lane B
sources (byte-pinned in the manifest, equivalence with the Lane B
oracles proven over 80 candidate documents spanning all benefit tasks,
controls, and use cases). Per-task budgets are 16 witness queries, 2
validation queries, 64 invocations, 120 s elapsed, 2 s per invocation,
64 KiB per message, at most 8 advances, identical for every arm-task
pair with no capacity transfer. A fresh process resumes from durable
receipts: a SIGKILL mid-task followed by a rerun reuses all settled
steps (no duplicate step receipts, reused receipts predate the resume)
and completes the panel checker-clean. Arms: A, the frozen greedy
reducer selected on development means; B, A plus a frozen
per-size-bucket ddmin/greedy selector; C, the shared-core compositions
with the frozen A fallback on refusal.

## 3. Mechanics verdict (authored fixtures)

The authored packages traverse real invocation, checking, persistence,
and later-use paths on 4 software plus 3 graph development tasks. Arm C
improves over the raw input on all 7 (verified, u 0.06-0.47) but loses
to the frozen baseline incumbent on all 7, by 0.29-0.55 on software and
0.06-0.21 on graphs. The apparatus is negative-capable: the gaps are
large, consistent, and computed live through the checker, not staged.
The four scope/validity controls (wrong observation, invalid sequence,
triangle graph, bipartite graph) all pass on all arms: no preserved
verdict anywhere and the delivered bytes are identical to the
incumbent. The core-substitution control (same adapters, no-search
core) scores u = 0 on both families, attributing C's improvements to
core proposals rather than adapter translation. An insufficient-encoding
pair (identical atom lists, differing witness observations) yields
identical core proposals but differing oracle verdicts, showing the
declared auxiliary material carries the distinction. Mechanics verdict:
the path works end to end; it shows no executable-retention advantage.

## 4. Acquisition and transfer (RPR-03/04/06)

Source acquisition covers the 6-task software context; transfer
development covers the 4-task graph context, which stays invisible to
source acquisition (barrier test on context bytes plus a checker audit
of source-stage inputs). The 2+2 acquisition pairs (B/C on `sw-che-00`
and `gr-che-00` with A references, fixed budgets, equal opportunity)
reproduce the mechanics pattern: C improves slightly (u 0.18 software,
0.06 graph, verified) while A/B reach 0.73/0.12. Transfer uses the
byte-identical core (`3185f9dd...` in both compositions, proved from
staged bytes, adapters differ); adaptation is confined to the disclosed
graph adapter. Acceptance is the byte-identical incumbent wherever no
verified improvement exists; no non-pilot acceptance occurred, so the
exact-oracle plus tiny-bytes plus construction-proof gate stands
untriggered and recorded. Trial success counts tie 9-9 under both
protocols (`inconclusive`); mean improvements lose everywhere, so the
preregistered promising-pilot rule fails and the disposition is
no release with persistent fallback: subsequent use selects the A
fallback on supported tasks (C stays trial-only even where it improved)
and the byte-identical incumbent on out-of-scope tasks. Acquisition
costs (289 shared transcript queries per deployed arm) plus panel costs
(A 136 queries, C 45 queries with 99 invocations and 29.6 s) are
reported at reuse horizons 1, 10, and 100 as explicitly hypothetical
projections; cheap invocation alone does not repay acquisition without
improvement, and none is observed. The physical operation union is 250
operations, counted once.

## 5. Live status

Blocked, externally. No `SETTLEMENT_GATEWAY_ENDPOINT`,
`SETTLEMENT_GATEWAY_KEY`, or grant (`SETTLEMENT_GRANT_UNITS`) is
configured, so the bounded campaign (12 calls, 16384 in / 8192 out
tokens each, 2 source + 2 transfer calls per arm, no retries, no
capacity transfer) has spent nothing and produced nothing. Exact
runnable command:

`SETTLEMENT_TEST_DSN=$SETTLEMENT_TEST_DSN .venv/bin/python experiments/representation/acquire/live_campaign.py --protocol rpr-acq-C --grant $SETTLEMENT_GRANT_UNITS --artifacts-root $ARTIFACT_ROOT`

which today exits 2 with the missing-inputs record. No model output
was faked, stubbed, or simulated; the deterministic results above do
not depend on the live phase.

## 6. Limitations

Seeded synthesis cannot show the underlying idea was absent from model
training; this pilot shows only that the authored coarse core plus
adapters lose to greedy baselines here. The transfer is finite-family
(C5/C7 patterns recur with held-out seeds; C9, shared-edge, and
joined-by-path patterns appear only in evaluation, which this pilot
does not consume). The oracle's `ok-preserved` does not enforce strict
decrease on non-incumbent candidates; all proposers here only shrink,
so reported `u` is unaffected. CPU time is not measured separately
from elapsed time; the resource clauses of the pilot rule are reported
from elapsed time, oracle queries, invocations, and zero model tokens.
Released-representation use is unexercised (nothing earned release).
The live campaign is fully blocked, so no claim about model
constructibility is made.

## 7. Reproduction

Prerequisites: real PostgreSQL 16, host-param DSN, the lane venv.
Freeze check: `.venv/bin/python
experiments/representation/experiment/freeze.py --check` (empty
problems). Fast verification without a database: `.venv/bin/python
experiments/representation/experiment/replay.py --mode check` (clean).
Full rerun from committed inputs: `SETTLEMENT_TEST_DSN=...`
`.venv/bin/python experiments/representation/experiment/replay.py
--mode run --tag <fresh-tag> --artifacts-root /tmp/... --staging-root
/tmp/... --runs-root /tmp/... --evidence-root /tmp/...` followed by the
checker with `--dsn`. Lane tests: the five `tests/test_rpr0[3468]_*.py`
files, 28 tests, on `settlement_cb01acq`. Manifest
`experiments/representation/experiment/manifest.json` (sha
`4674f918...`) pins all 31 input files, 4 compositions, selectors,
panel, budgets, and protocols; evidence carries per-arm-task
composition digests, invocation receipts, oracle queries, costs, trial
refs, and dispositions.
