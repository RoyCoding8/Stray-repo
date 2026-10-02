# Engineering review and repair — coordinator index

Assignment: `WORKER-ENGINEERING-REVIEW.md` (whole-repository review,
priorities P0–P4, techniques A–H). Coordinator branch:
`codex/implementation-development-02`. Base for all lanes: `9ee00a6`
(merge of `origin/codex/development-02-live-evidence`, itself based on
live-campaign tip `3857ec4`). Prior obligations carried forward:
EVID-01 (solver output contract), EVID-02 (unbilled-usage reporting)
from `reviews/DEVELOPMENT-02-LIVE-EVIDENCE.md`.

Shared contracts (coordinator-owned; lanes request changes, never edit):
`src/settlement/common.py`, `src/settlement/gateway.py`,
`src/settlement/db.py`, `src/settlement/config.py`, `pyproject.toml`,
`uv.lock`, migration numbering, `reports/PLAN.md`, this file,
`reports/VERIFICATION.md`, `reports/IMPLEMENTATION-STATUS.md`,
`reports/DECISIONS.md`, `reviews/REQUEST.md`, `docs/design/*`
(read-only except `REFINEMENT-ROADMAP.md` at handoff).

Region partitions inside shared implementation files (function-level,
no two lanes edit the same region):
`src/settlement/experiment.py`: ENG-ACCT owns `_op_accounting`,
`_settle_costs`, cost-union and report-accounting assembly;
ENG-SOLV owns `_arm_prompt`, collection/arm/use text→source paths
(`_prepare_grade`, `_invoke_method` input handling,
`run_subsequent_use` incumbent consumption); ENG-INV-C reads the
rest and reports findings to the region owner.
`src/settlement/development.py`: ENG-SOLV owns collection text
consumption; ENG-INV-C reads the rest and reports.
`src/settlement/gateway_http.py`, `broker.py`, `store.py`,
launchers: ENG-INV-B owns (findings about gateway/billing semantics
go to ENG-ACCT; solver-contract needs go to ENG-SOLV).

## Lanes

| ID | Obligation | Branch / worktree | Owned paths | Test DB |
|---|---|---|---|---|
| ENG-ACCT | EVID-02: unbilled reporting reconciled to durable settlement; monetary unknown unless decoded; migrate characterization to real-DB check | `codex/eng-acct` / `/tmp/asv2-eng-acct` | experiment.py accounting regions, owned tests | `settlement_engacct` |
| ENG-SOLV | EVID-01: shared solver output contract + validation policy; raw preservation; failure classification; live baseline smoke (one task, finite grant, disposable profile) | `codex/eng-solv` / `/tmp/asv2-eng-solv` | experiment.py arm/collection/use regions, development.py collect region, owned tests/fixtures | `settlement_engsolv` |
| ENG-PROV | Effective-config export + source fingerprint in entry records; evidence-bundle manifest | `codex/eng-prov` / `/tmp/asv2-eng-prov` | run_dev_episode.py + run_use.py + run_live_abc.py record regions, owned tests | `settlement_engprov` |
| ENG-INV-A | Inventory + P0–P4 sweep: durability, recovery, ops | `codex/eng-inva` / `/tmp/asv2-eng-inva` | store.py, run.py, scripts/*, migrations 0001/0004/0006 (numbering via coordinator), owned tests | `settlement_enginva` |
| ENG-INV-B | Inventory + P0–P4 sweep: dispatch, containment, gateway | `codex/eng-invb` / `/tmp/asv2-eng-invb` | broker.py, gateway_http.py, boot.py, exec_profile.py, launcher_*.py, owned tests | `settlement_enginvb` |
| ENG-INV-C | Inventory + P0–P4 sweep: evidence, learning, operator, packaging | `codex/eng-invc` / `/tmp/asv2-eng-invc` | artifacts/evidence/context/capabilities/trials/evaluation/steward/agenda/api.py, experiments/*, migrations others (via coordinator), templates/static/config-example/README (read-only, requests only), owned tests | `settlement_enginvc` |

Integration order: ENG-PROV + ENG-INV-* (independent) → ENG-ACCT →
ENG-SOLV (contract decision gates its implementation; smoke last).
Merges one at a time with affected checks rerun. Final: journey pass
+ failure-mode pass + full suite on the integrated tip.

## Coverage matrix

Status key: pending / assessed / fixed+verified. Lanes fill evidence
and disposition; coordinator reconciles against the final tree.

| Subsystem | Files | Owner | Status |
|---|---|---|---|
| command/result envelope, errors | src/settlement/common.py | coordinator (frozen) | assessed |
| gateway ABC + fake | src/settlement/gateway.py | coordinator (frozen) | assessed |
| DSN/connect/migrate | src/settlement/db.py | coordinator (frozen) | assessed |
| typed settings | src/settlement/config.py | coordinator (frozen) | assessed |
| durable state, reservations, settlement | src/settlement/store.py | ENG-INV-A | fixed+verified (173798f → 7bc7fe0; INVA-01/02) |
| workflow engine | src/settlement/run.py | ENG-INV-A | assessed (INVA-05 max_depth note ledgered) |
| ops scripts | scripts/checkpoint.py, restore.py, scheduler.py, manifest.py, probe_sandbox.py | ENG-INV-A | assessed (scheduler P4 nits ledgered; authority fixture fixed CLOSE-1, green both DSN forms) |
| closure repairs | store/run/db/evidence/gateway/doubles + authority fixture | CLOSE-1 + coord | fixed+verified (INVA-03/04/05/06/08, INVB-11 pin/13, check_use, doubles) |
| base/recovery migrations | migrations/0001_schema.sql, 0004_leases.sql, 0006_recovery_fence.sql | ENG-INV-A | assessed |
| dispatch/supervision/reconcile | src/settlement/broker.py | ENG-INV-B | fixed+verified (71d34a4 → 5c5cd1f; INVB-01/02/06) |
| HTTP gateway both APIs | src/settlement/gateway_http.py | ENG-INV-B | fixed+verified (INVB-03; INVB-10 filed to ACCT) |
| boot/profiles | src/settlement/boot.py, exec_profile.py | ENG-INV-B | fixed+verified (INVB-04; INVB-08 rebutted) |
| launchers | src/settlement/launcher_local.py, launcher_runsc.py | ENG-INV-B | fixed+verified (INVB-05/07/09; INVB-11/12 notes; runsc shim-only) |
| billing report surface | experiment.py accounting regions | ENG-ACCT | fixed+verified (dbaee1a → 0cf6786; oracle follow-up e6a8848) |
| solver text→source | experiment.py arm/collection/use regions, development.py collect region | ENG-SOLV | fixed+verified (eaa93b0 → fea7de7; probe follow-up 3439e8b; D-ENG-SOLV-01 approved) |
| artifacts/bytes | src/settlement/artifacts.py | ENG-INV-C | fixed+verified (847c39d → e9dc384; INVC-04/05/06/07) |
| evidence/claims/warrants | src/settlement/evidence.py | ENG-INV-C | assessed, no change |
| context packets/binding | src/settlement/context.py | ENG-INV-C | fixed+verified (INVC-09 fail-closed bind) |
| capabilities/router/release | src/settlement/capabilities.py | ENG-INV-C | fixed+verified (INVC-08 bounded errors; INVC-10 pinned) |
| trials/comparison | src/settlement/trials.py | ENG-INV-C | fixed+verified (INVC-01/02; INVC-11 rebutted for prod) |
| evaluation/grading bind | src/settlement/evaluation.py | ENG-INV-C | fixed+verified (INVC-03 version pin) |
| episode lifecycle/check/select | src/settlement/development.py (non-collect) | ENG-INV-C (report-only) | assessed, no change |
| experiment orchestration | src/settlement/experiment.py (non-acct/solver) | ENG-INV-C (report-only) | assessed, no change |
| operator/API/agenda | src/settlement/steward.py, agenda.py, api.py | ENG-INV-C | assessed, no change |
| entry points | experiments/run_dev_episode.py, run_use.py, run_live_abc.py, run_tests.py | ENG-PROV (records; c0fd039) + ENG-INV-C (semantics) + CLOSE-1 (run_tests.py live end-to-end: 2 pass/1 fail of 3, docstring accurate) | assessed |
| fixtures/doubles/tasks | experiments/doubles.py, fault_tasks.py, dev01_tasks.py, dev02_challenge.py, offbyone_fixer.py | ENG-INV-C + CLOSE-1 | fixed+verified (unknown-task GatewayError; rest assessed) |
| learning/eval migrations | migrations/0002/0003/0005/0007/0008/0009 | ENG-INV-C (numbering via coordinator) | assessed, no numbering change |
| packaging/install | pyproject.toml, uv.lock, config/.env.example, README.md | coordinator + ENG-INV-C (read-only) | CLOSED (dead asyncio key dropped 46427f4, verified no plugin/tests) |
| UI/templates/static | templates/, static/ | ENG-INV-C (read-only) | CLOSED (dead learning.html sections dropped b1dece4; overview truthful) |
| tests + probes | tests/, reviews/probes/ | owning lane each; coordinator reconciled | CLOSED: 590 green closure suite; 4 probe files green (27, CLOSE-1); historical pilots intentionally uncollected. Agenda slice adds 63 (state 14, policy 27, experiment 18, demo 4); full suite 653 green on the agenda tip — see `reports/AGENDA-01.md` |
| active docs/reports | docs/design/*, reports/*, reviews/*, WORKER-*.md | read-only (roadmap at handoff) | checked (agenda integration: ledger duplicates merged, superseded rows mapped to CLOSE-1, `reports/AGENDA-01.md` added; historical dispositions preserved) |

## Findings ledger

| ID | Priority | Trigger | Expected / actual | Disposition |
|---|---|---|---|---|
| EVID-01 | P1 | review assessment §EVID-01 + live C-ep-04 prose-trapped fixes | solver outputs need a shared validated source contract / raw text graded as source, format confound unmeasured | CLOSED: contract implemented (eaa93b0 lineage) + direct probe on final tree (CLOSE-1: classification + verbatim preservation under SOLVER_SOURCE_CONTRACT) |
| EVID-02 | P1 | review assessment §EVID-02 + doubled-DB probe | unbilled usage must reconcile to durable settlement, money unknown unless decoded / `_op_accounting` reports charge 0 as settled 0 | CLOSED: reconciled reporting (dbaee1a lineage) + direct probe on final tree (CLOSE-1: unbilled settles reserved billed=False; billed settles charge) |
| EVID-PROV | P3 | assessment provenance section: records say `976cee1`/512 for working-tree runs | entry records must pin effective source hash + effective caps / revision + label caps only | CLOSED: fingerprint + effective-config in records (c0fd039 lineage), verified by read on final tree (CLOSE-1) |
| CLOSE-1-03 | P3 | negative `seed_allocation` inputs (INVA-03) | bounded result / raw CheckViolation | fixed+verified CLOSE-1 (app-side positivity, red-capable) |
| CLOSE-1-04 | P3 | post-settlement cross-identity contradiction (INVA-04) | flagged / stored unflagged | fixed+verified CLOSE-1 (conflict shape mirrors INVA-01) |
| CLOSE-1-05 | P4 | unenforced `max_depth` (INVA-05) | enforced in validate + routed in attempt_workflow | fixed+verified CLOSE-1 |
| CLOSE-1-11 | P4 | broker `cwd` admission pin (INVB-11) | executable refusal pin | verified (refusal predates; pin committed, 20 green together) |
| CLOSE-1-13 | P4 | dead `_decode` (INVB-13) | deleted, zero callers | verified |
| CLOSE-1-CU | P4 | future-epoch `check_use` (INVC-12) | refuse mismatch | fixed+verified CLOSE-1 |
| CLOSE-1-DB | P4 | double KeyError on unknown task (INVC-12) | bounded GatewayError | fixed+verified CLOSE-1 |
| ENG-INVA-01 | P1 | replayed receipt-identity against a different operation | refuse or conflict-record / ACKed as duplicate of the wrong op, evidence dropped | fixed+verified (173798f → 7bc7fe0) |
| ENG-INVA-02 | P2 | `reconcile_operation` on merely-`prepared` op | refuse, nothing dispatched / stranded as `reconciled`, op undispatchable | fixed+verified (173798f → 7bc7fe0) |
| ENG-INVA-03 | P3 | negative `seed_allocation` inputs | bounded `CommandResult` / raw `CheckViolation` leaks | SUPERSEDED by CLOSE-1-03 (fixed+verified, app-side positivity, red-capable) |
| ENG-INVA-04 | P3 | post-settlement contradictory receipt under new identity | flagged contradiction / stored unflagged, `reconcile_state` stays `none` | SUPERSEDED by CLOSE-1-04 (fixed+verified, conflict shape mirrors INVA-01) |
| ENG-INVA-05 | P4 | `Composition.max_depth` on initial validation | enforced bound / enforced only by `revise()` | SUPERSEDED by CLOSE-1-05 (fixed+verified, enforced in validate + routed) |
| ENG-INVA-06 | P4 | read-only store/run paths under wedged DB | bounded waits / no timeouts, unlike `transact` | ledgered, then fixed+verified (coord: shared `db.read_connect`, 10s connect + 60s statement, 9 sites; mechanism test + consumer suites green) — single authoritative row; earlier ledger entry merged here |
| ENG-INVA-07 | P4 | journal/events/outbox/continuation growth | pruning or bounds / unbounded | ledgered, then justified no-change: deletion risks evidence/recovery obligations (retirement/archival/deletion are distinct operations per design); no retention policy exists to implement against — capacity planning stays future work, fail direction is safe (full disk errors, never silent loss) — single authoritative row; earlier ledger entry merged here |
| ENG-INVA-08 | P3 | `test_r02_authority.py` sibling-DB DSN construction | parseable DSN / `urlunsplit` drops `//` on empty netloc | fixed+verified CLOSE-1 (+coord setdefault: explicit params win; green URL + keyword forms) |
| ENG-INVA-09 | P4 | `_connect_before` orphaned attempt on deadline | closed on expiry / daemonized socket leaks until GC | justified no-change: bounded (one socket per expiry), GC-reclaimed, no correctness effect; coordination machinery would exceed the fault |
| ENG-INVA-06/07 duplicates | P4 | duplicate ledger rows merged into the authoritative ENG-INVA-06/07 rows above | — | merged, no separate disposition || ENG-INVC-01 | P2 | trials `assign` retry with new request id | bounded result / raw `UniqueViolation` | fixed+verified (847c39d → e9dc384) |
| ENG-INVC-02 | P2 | assignments on unfrozen protocols | refuse unless frozen / freeze only a DB trigger | fixed+verified (847c39d → e9dc384) |
| ENG-INVC-03 | P3 | evaluator re-registration with different version | refuse / APPLIED keeping old version | fixed+verified (847c39d → e9dc384) |
| ENG-INVC-04 | P2 | artifact quota after purge | purged rows excluded / consumed quota forever | fixed+verified (847c39d → e9dc384) |
| ENG-INVC-05 | P2 | package receipt `size` vs digest | size covered / tampered size stored | fixed+verified (847c39d → e9dc384) |
| ENG-INVC-06 | P2 | `reconcile_staging` crash orphans | logical manifest+size / full receipt as manifest | fixed+verified (847c39d → e9dc384) |
| ENG-INVC-07 | P2 | archive extraction symlinks/perms | rejected, no-same-owner / absolute symlink materialized | fixed+verified (847c39d → e9dc384) |
| ENG-INVC-08 | P3 | capability entry extraction failures | bounded `SettlementError` / raw `StopIteration` etc. | fixed+verified (847c39d → e9dc384) |
| ENG-INVC-09 | P3 | packet bind to non-inference op | require `MODEL_INFERENCE` / unknown effects passed | fixed+verified (847c39d → e9dc384) |
| ENG-INVC-10 | P4 | familyless release matching | pinned by tests, no production consumer | ledgered, no change |
| ENG-INVC-11 | P4 | direct `record_result` path bypassing receipts | unreachable in production (bound path + release gate) | rebutted for prod |
| ENG-INVC-12 | P4 | assorted edge semantics (epochs, orphans, auth seams, verdict) | each probed/read to disposition | ledgered |
| ENG-INVC-13 | P3 | `learning.html` hardcoded empty-state text | render from data or drop / hardcoded despite comparisons | CLOSED (dead sections dropped b1dece4) |
| ENG-INVC-14 | P4 | `asyncio_mode=strict` with no plugin | add plugin or drop key / warns every run | CLOSED (key dropped 46427f4) |
| ENG-INVC-15 | P4 | parallel lanes sharing one DB corrupt via TRUNCATE | per-agent DB names / shared lane DB | process note for coordinator |
| ENG-INVB-01 | P2 | raising gateway escapes `dispatch_operation` | contained as unknown-receipt/unresolved, exposure retained | fixed+verified (71d34a4 → 5c5cd1f) |
| ENG-INVB-02 | P2 | `request_cancel` never reached gateway | gateway param + api.py wire-up (0d34527, red-checked) | fixed+verified |
| ENG-INVB-03 | P2 | `infer` waited full deadline after cancel | 50ms wait slices, prompt CANCELLED | fixed+verified |
| ENG-INVB-04 | P2 | no setsid, child-only kill; timeout blocked on pipe EOF | group kill TERM/grace/KILL; PID-reuse-safe supervisor | fixed+verified |
| ENG-INVB-05 | P3 | stale-generation refusal left blocking pid claim | unlink own claim on that path | fixed+verified |
| ENG-INVB-06 | P3 | `ensure_operation(retries=None)` uncaught TypeError | INVALID_INPUT for non-int/negative | fixed+verified |
| ENG-INVB-07 | P3 | pgrep-flake in group-kill test | pid-file observation rewrite, no pgrep | fixed in test |
| ENG-INVB-08 | P3? | password-bearing DSN in boot errors | libpq never echoes password | rebutted |
| ENG-INVB-09 | P2 | `read_output` missing relpath check | factored `_check_relpath` applied | fixed+verified (sibling hunk, adopted 71d34a4) |
| ENG-INVB-10 | P2 | responses path never bills; unbilled chat settles cost None | billing semantics | CLOSED as deliberately unchanged (D-ENG-02): direct probe confirms fail-visible conservative settlement; no billing oracle to validate a change |
| ENG-INVB-11 | P4 | broker rejects `cwd` keys but launcher honors them | unreachable via public path | noted, no change |
| ENG-INVB-12 | P3 | stale `.container` tracks misreport runsc liveness | exposure-safe direction; repair wedges | observation, coordinator decision |
| ENG-INVB-13 | P4 | dead `_decode` variant | no callers | SUPERSEDED by CLOSE-1-13 (verified: deleted, zero callers) |

## Closure (WORKER-ENGINEERING-CLOSURE.md)

- CLOSE-1 (`codex/eng-close1` → merged): INVA-03/04/05/08, INVB-11 pin/13,
  check_use/doubles fixes with red-capable regressions; EVID-01/02/PROV
  closed by direct probe; entry-points/tests-probes rows assessed.
  Report: `reports/workstreams/eng-close1.md`.
- Coordinator: INVA-06 bounded read waits (`db.read_connect`); INVA-07/09
  justified no-change with exact bounds; authority fixture setdefault fix;
  api.py gateway wire-up (INVB-02) with red-checked test.
- CLOSE-2 (`codex/eng-close2` → merged): one bounded live baseline smoke
  on repaired tree, success, reconciled bundle at
  `reports/evidence/eng-close2/`; historical smoke annotated, preserved.
- Ledger above is final: every finding is fixed+verified, rebutted with
  evidence, or justified no-change. Open only: PG18, real runsc
  containment, live selected-method transfer/learning (externally
  blocked or no live subject), INVA-08-style fixture hardening beyond the
  canonical DSN (future test-infra).
