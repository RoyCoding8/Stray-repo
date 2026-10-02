# ENG-INV-C workstream — evidence/learning/operator/packaging sweep

Base: `f478143`. Report commit tip: see `git log codex/eng-invc`
(this report + `tests/test_eng_invc.py` committed on top of `43ea6f3`).
DB: `settlement_enginvc` (real PostgreSQL 16.15). Python 3.12.3.
Skill: diagnosing-bugs (probe-first; every P0–P2 fix has a real-PG probe
plus a regression that goes red on base sources).

## Process note (lane-integrity collision)

At ~12:38–12:43 UTC a second writer edited and committed in this
worktree/branch (`e093ddc`, private identity, lane-scoped message).
That commit swept in uncommitted edits of mine (trials/evaluation/
artifacts) together with its own fixes to my owned files
(artifacts `_contained`/`_reject_untrusted_extraction`/`--no-same-owner`/
tmp-grace/manifest-shape/`verify_bytes` unknown-digest guard,
capabilities `_extract_entry`, context effect check). I preserved all of
it, verified each adopted hunk with an independent probe or test, added
the two missing pieces (publish size binding, reconcile logical size),
and covered everything with `tests/test_eng_invc.py` (8/8 red on base
sources, 8/8 green on the fixed tree). Concurrent test runs against the
shared lane DB caused one flaky interference episode (TRUNCATE races in
fixtures); final gates were rerun to green. Coordinator: please confirm
single ownership of `codex/eng-invc` before integration.

## Fixes (all verified: probe + regression + suite)

| ID | P | File | Defect | Fix |
|---|---|---|---|---|
| ENG-INVC-01 | P2 | trials.py `assign` | retry with a new request id raised raw `UniqueViolation` instead of returning a result | pre-select inside txn; existing row returns `ALREADY_APPLIED` with the prior `blind_key` |
| ENG-INVC-02 | P2 | trials.py `assign` | assignments accepted on unfrozen (draft/amend-intermediate) protocols; freeze was only a DB UPDATE trigger | refuse when `protocol.frozen` is false |
| ENG-INVC-03 | P3 | evaluation.py `register_evaluator` | re-registering an id with a different version returned APPLIED while keeping the old version | refuse version change under an existing id |
| ENG-INVC-04 | P2 | artifacts.py `_scope_used` | purged rows kept consuming quota forever (probe: used=1 after purge) | exclude `retention_state = 'purged'` |
| ENG-INVC-05 | P2 | artifacts.py `publish_package` | receipt `size` was not covered by the package digest; tampered size 0 stored (probe) | verify receipt size equals manifest sum; re-validate manifest paths at publish |
| ENG-INVC-06 | P2 | artifacts.py `reconcile_staging` | crash orphans registered with the full receipt as `manifest` and envelope bytes as `size` | store receipt `manifest` and digest-bound logical size (shape fix adopted, size mine) |
| ENG-INVC-07 | P2 | artifacts.py `_unpack_archive_isolated` | absolute-target symlink materialized in staging (probe); tar ran with owner/perms preserved | reject links/specials post-extract, `--no-same-owner/--no-same-permissions` (adopted; my probe + test) |
| ENG-INVC-08 | P3 | capabilities.py `_extract_entry` | package without a `.py` entry raised raw `StopIteration` (probe) | map `ValueError/KeyError/StopIteration` to `SettlementError` (adopted; my probe + test) |
| ENG-INVC-09 | P3 | context.py `bind_packet_invocation` | any non-listed effect (including a missing one) passed as model inference | require `effect == MODEL_INFERENCE` (adopted; broker guarantees effect, verified) |

## Ledger (no code change, with evidence)

- ENG-INVC-10 (P4): `releases_for_scope` familyless releases match every
  family query; empty family returns all. No production consumer (only
  tests); semantics pinned by existing tests. Left as is.
- ENG-INVC-11 (P4): `trials.record_result` direct-caller path feeds
  `verdict()` without evaluator receipts, and the UI `simulated` flag
  only inspects receipts. Production (`experiment.py` `_open/_close_
  assignment`) uses exclusively the bound submit/bind/receipt path, and
  the release gate refuses synthetic/direct origins — so this is
  unreachable in production. Rebutted for production; harness-only.
- ENG-INVC-12 (P4 group, assessed, each probed or read to disposition):
  `check_use` tolerates a future epoch (comparison only guards stale);
  `save_continuation` can orphan artifact bytes if the txn raises;
  `amend_protocol` flips `frozen` in a separate autocommit UPDATE;
  `register_observation` authentication is caller-attested
  non-empty identity (documented seam; callers live in read-only files);
  `operator_token` prints the fallback token to stdout (documented);
  `investigation_data` omits claim/artifact-only derivations from the
  view; `doubles.ScriptedDouble` raises `KeyError` on unknown tasks
  (harness-only); `verdict` on an empty protocol is `inconclusive`
  (intended); `freeze_protocol` duplicates refused in-txn (tested).
- ENG-INVC-13 (P3 change request, templates/ read-only):
  `templates/learning.html` hardcodes "demonstrated gains: none
  recorded" / "experimental alternatives: none recorded" even when
  comparisons exist. Request: render from `view.comparisons` or drop
  the dead sections. Overview template verified truthful (counts with
  showing-X-of-Y, unresolved ops, packet gaps/next actions).
- ENG-INVC-14 (P4 change request, pyproject read-only): `asyncio_mode =
  "strict"` warns on every run (`Unknown config option`) because no
  asyncio plugin is installed. Request: add the plugin or drop the key.
- ENG-INVC-15: lane-DB sharing hazard — duplicate concurrent runs
  against one lane DB corrupt each other through TRUNCATE fixtures
  (observed). Suggest per-agent DB names for parallel lanes.

## Coverage matrix (techniques A–H as applicable; R = read-only)

| File | Techniques | Evidence | Disposition |
|---|---|---|---|
| artifacts.py | A,B,C,D,F,G,H | probes 5,6,7,A,C + 4 regressions + suite | fixed+verified |
| evidence.py | A,B,C,E,F | read; warrant/opposition/epoch paths covered by test_s2_evidence + epoch tests | assessed, no change |
| context.py | A,B,D,E,F,G | read; effect-check adopted; bind replay via development.py:533-545 + d02live tests | fixed+verified |
| capabilities.py | A,B,D,E,F | probes 8,B; release double-check read; router/evaluate covered by tests | fixed+verified |
| trials.py | A,B,C,E,F | probes 1,2,4 + 2 regressions + suite | fixed+verified |
| evaluation.py | A,B,D,E,F | probe 3 + 1 regression + evalbind tests | fixed+verified |
| steward.py | A,C,D,G | read; lease/amend/delegate paths covered by steward/lease tests | assessed, no change |
| agenda.py | A,G,H | read only; no mechanism changes per scope | assessed, no change |
| api.py | A,D,G | read + empty-DB overview probe; command/UI tests green | assessed, no change |
| doubles.py | E,F | read; simulated-flag discipline intact | assessed, no change |
| fault_tasks.py | E,F | read; families disjoint by construction | assessed, no change |
| dev01_tasks.py | E,F | read; guard family disjoint from loop-bound/operator faults | assessed, no change |
| dev02_challenge.py | E,F | read; static frozen panel | assessed, no change |
| offbyone_fixer.py | D,F | read; rewrites idempotent on fixtures | assessed, no change |
| run_tests.py | D,F,G | read + live float-fixture grader run (pass); isolation claim accurate only inside the outer sandbox — docstring states the child step | assessed, no change |
| migrations 0002/0003/0005/0007/0008/0009 | A,C,H | read; apply cleanly on lane DB; 0009 uses IF NOT EXISTS | assessed, no change |
| experiment.py (R) | A,E | S3 open/close/release paths use bound receipts; release skips synthetic | findings to ENG-SOLV/ACCT: none new |
| development.py (R) | A,E | packet ready-gate + pre-dispatch bind; comparison_exposed guards intact | findings to owner: none new |
| run_dev_episode/run_use/run_live_abc (R) | A,G | live_abc refuses without endpoint/containment; report labeled simulated | assessed, no change |
| templates/static (R) | G | overview truthful; learning.html dead sections → ENG-INVC-13 | change request |
| config/.env.example, README (R) | G,H | example matches unset-safe defaults; README has no install commands to verify | assessed |
| pyproject/uv.lock (R) | G | sync+build green; asyncio warning → ENG-INVC-14 | change request |

## Checks

- `uv sync --extra test`: green.
- New `tests/test_eng_invc.py`: 8/8 green on fixed tree; 8/8 red on
  base-source overlay (`PYTHONPATH=/tmp/basecheck/src`,
  DB `settlement_invcbase`).
- Focused + neighboring files (28 files: test_eng_invc, s2_*,
  s3_*, operator_review, ui_views, ui_commands, agenda_policy,
  agenda_repair, steward_leases, r01_deadline_ui, dev02_context,
  d02live_context, dev02_episode, d02live_episode, evidence_epoch,
  learning_review, r01_evidence, r01_experiment, r01_grader,
  r02_evalbind, r01_release, dev01_compare): **212 passed**
  at tip `43ea6f3` (6:10). An earlier 200/12 run failed from
  concurrent-writer DB interference plus a stale bind test; both
  resolved (single quiet run + `43ea6f3` test fix), then rerun green.
- `uv build`: sdist+wheel build; outputs removed after.
- Live inference: none performed (no endpoint/credentials); all claims
  rest on real-PG deterministic runs.
- Bounds: no clean-container install; no browser UI pass; duplicate
  lane-DB interference possible until single ownership confirmed.
