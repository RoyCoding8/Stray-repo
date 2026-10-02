# Workstream cbr01: CBR-01 real acquisition orchestration (Lane D)

Branch: `wt/cbr01`. Author `Nightjar <nightjar@authors.invalid>`. Lane
test DB `settlement_cbr01`, real PostgreSQL, host-param DSN
`postgresql://ubuntu@/settlement_cbr01?host=/var/run/postgresql`.
No live model calls, no credentials anywhere in this lane; all
construction responses come from deterministic constructor doubles
through the production entry.

## Owned paths

- `experiments/representation/acquire/campaign.py` (new, production
  orchestration entry)
- `experiments/representation/acquire/live_campaign.py` (rewritten
  around the orchestration; legacy exact-blocker shape preserved)
- `tests/test_rpr10_campaign.py` (new gate)
- `reports/workstreams/cbr01.md` (this file)

No edits outside this scope. No new tables, no new framework, no
changes to broker/artifacts/profile/runner semantics.

## Root cause

`live_campaign.py` returned a blocked record for missing and fully
supplied configuration alike, and `--grant` never reached `preflight`.
The unconditional `awaiting-authorization` block stood in for grant
admission, and no construction/dispatch/parse/stage/execute path
existed behind it.

A second, load-bearing defect surfaced during implementation:
`control.authority_version` defaults to 1 on a fresh database, so an
`authority_version < 1` check can never fire. Durable authority is the
`grants` table row at the current authority version; credentials plus
config values alone still block with `no-installed-grant`.

## Invariant restored

Configured campaigns run the fixed 12-call construction plan (2 source
+ 2 transfer per arm, retries 0, 8192 max output tokens and 16384 input
tokens per call, no capacity transfer) through broker-dispatched
model-inference operations under a precomputed grant-backed allocation.
Parsed responses become the staged, published and executed bytes via
the existing `representation-01` profile runner; refusals, ignored
responses and transport errors abstain explicitly with the call budget
still consumed. Source selection freezes the core before transfer
prompts are built; transfer `core.py` bytes are refused and the frozen
bytes stage instead. Authored fixtures never enter except inside a
model response receipt, so a planted authored composition cannot be
selected or executed.

## Verification

- `tests/test_rpr10_campaign.py`: 11 passed on real PostgreSQL.
  Useful double (executed candidates, 12-op audit, digest chain),
  always-refusing double (abstention, equal-opportunity spend kept),
  ignored-response double (`not-json` / `wrong-kind`), planted
  authored composition (not selected, not executed, not referenced),
  core-change refusal (frozen digest kept), tiny allocation (refused
  before dispatch, zero gateway calls), missing durable grant
  (blocked despite config), transport error (slot error, arm
  continues), CLI `--grant` overriding env into orchestration.
- `tests/test_rpr08_evidence.py`: 5 passed (exact-blocker shape,
  committed evidence still checker-clean, full panel untouched).
- `tests/test_rpr06_transfer.py`, `tests/test_rpr05_runner.py`:
  18 passed (depended-on transfer/runner semantics corroborated).
- Assessment probe with placeholder config now reports the real
  requirement check (`grant-below-requirement`) instead of the
  unconditional block; `--help` exposes the full configured entry.

## Boundaries

Deterministic doubles prove the orchestration, not live acquisition.
A/B text and procedures publish as artifacts but have no execution
profile; only C bytes execute. Live runs additionally need a seeded
grant, a funded allocation, gateway reachability/auth and `--model`.
Held-out evaluation (CBR-02) and the full decision rule (CBR-03) are
separate workstreams and untouched here.
