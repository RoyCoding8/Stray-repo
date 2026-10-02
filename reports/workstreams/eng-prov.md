# Workstream ENG-PROV: entry records pin effective source + runtime config

Branch: `codex/eng-prov`, base `f478143c520977da179cef3da309824a996a42cb`,
record-assembly change `a290dcae12ee305d28cb5d9031717382270626ce`;
branch tip is this report commit (see `git log codex/eng-prov`).
Scope: record-assembly regions only — `experiments/run_dev_episode.py`,
`experiments/run_live_abc.py`, `experiments/run_use.py`, plus owned tests in
`tests/test_dev01_ops.py`. No product-logic, gateway, store, broker, contract,
coordinator-report, or docs/design changes. Identity `Nightjar` verified, unchanged.

Obligation: `reviews/DEVELOPMENT-02-LIVE-EVIDENCE.md` provenance section —
entry records reported revision `976cee1` for working-tree runs and
`budgets.*.matched_caps.tokens=512` while effective caps were 8192.

## Ledger

- ENG-PROV-01: `_source_fingerprint()` (`run_live_abc.py`) pins revision
  (full SHA, `unknown` off-git), dirty flag, sha256 tree hash over
  `status --porcelain` + `diff HEAD`, and dirty-file count. Replaces the
  SHA-only `_revision()` in `run_dev_episode.py` (deleted).
- ENG-PROV-02: `_effective_config()` (`run_live_abc.py`, single source,
  imported by the other two entries) pins gateway api (`adapter.api`,
  `fixture` default), endpoint/key configured booleans only (never values),
  gateway timeout overrides, model requested/returned ids (fixture:
  `scripted`/`scripted`; live: requested id, returned null with receipts
  pointer), as-used budgets (`model_token_budget()`,
  `development.packet_budget()`, `GRADER_TIMEOUT_MS/MAX_BYTES`), grant units
  + allocation, launcher profile/request/allow-uncontained/exposure
  (`contained` iff profile `gvisor`, else `uncontained`) + runsc image pin.
- ENG-PROV-03: `run_dev_episode` record gains top-level `source` +
  `effective_config`; `use` phase detail carries the child `run_use`
  provenance. `report["budgets"]` label constants are left verbatim so the
  label-vs-effective divergence stays explicit, not relabeled.
- ENG-PROV-04: `run_live_abc` record gains `source` + `effective_config` and
  now writes `<prefix>-abc.json` beside stdout. `run_use` output gains
  `source` + `effective_config` (grant null with parent-record note).
- ENG-PROV-05: `_bundle_manifest()` documents the `d02-evidence-bundle-v1`
  layout (entry JSON with effective config, `<prefix>-manifest.json` with
  record sha256 + artifact inventory, `<prefix>-dump.sql` via
  `pg_dump "$SETTLEMENT_DSN"`, staged artifacts). Both top-level entries
  write the manifest; DSN/endpoint/key values never enter records.
- ENG-PROV-06: tests — 3 helper tests (fingerprint vs independent git,
  fixture/contained mapping incl. defaults 512/24000, manifest layout) + 1
  real-PG fixture episode with `SETTLEMENT_MODEL_TOKENS=8192`,
  `SETTLEMENT_PACKET_BUDGET_CHARS=31337`, timeout override, and marker
  endpoint/key asserting effective caps in record + use phase, label
  constants preserved, manifest sha match, and zero secret leakage.

## Checks (worktree /tmp/asv2-eng-prov, DB settlement_engprov)

- `uv sync --extra test` — ok.
- `SETTLEMENT_TEST_DSN=postgresql:///settlement_engprov?host=/var/run/postgresql uv run --extra test python -m pytest tests/test_dev01_ops.py tests/test_r01_experiment.py tests/test_learning_review.py -q` — 24 passed.
- Deterministic `run_live_abc` on scratch PG with `SETTLEMENT_MODEL_TOKENS=8192`: record shows `tokens 8192`, `api fixture`, `local-process/uncontained`, dirty tree hash; `m-abc.json` + `m-manifest.json` written (scratch DB/artifacts removed after).
- `uvx ruff check` on the 4 files: 7 errors, all pre-existing at base (net -1: deleted `_revision` subprocess call; my 2 new call sites carry explicit `check=False`).
- No live inference: fixture adapter + real PG only. Cost note: the 8192-token setting genuinely raises per-op reservations (a 100k seed grant refuses mid-episode); the PG test seeds 5M.

## Re-verification (second pass, same worktree)

- ENG-PROV-07: `settlement_engprov` reachable; `uv sync --extra test` ok.
- `SETTLEMENT_TEST_DSN=postgresql:///settlement_engprov?host=/var/run/postgresql uv run --extra test python -m pytest tests/test_dev01_ops.py tests/test_r01_experiment.py tests/test_learning_review.py -q` — 24 passed.
- Independent fixture episode on real PG (`SETTLEMENT_MODEL_TOKENS=8192`,
  `SETTLEMENT_PACKET_BUDGET_CHARS=31337`,
  `SETTLEMENT_GATEWAY_TIMEOUT_READ_MS=12345`, marker endpoint/key): record
  shows `dirty True` + 64-char `tree_hash`, `api fixture`, effective
  `model_tokens 8192` vs label `matched_caps.tokens 512`,
  `packet_chars {input_chars 31337, output_reserve 2000}`,
  `timeouts {connect 5000, read 12345, total 300000}`,
  `model scripted/scripted`, grant units 0 + allocation,
  `launcher local-process/uncontained`; marker secrets absent from record.
- `uvx ruff check` on the 4 files: 7 errors; base copies of the same 4
  files show 8 (`--isolated`, scratch dir, no tree contact) — net -1
  (deleted `_revision` unchecked `subprocess.run`; new call sites use
  `_git_output` with explicit `check=False`). No new lint debt; left as-is.
- No live inference (fixture adapter + real PG only); no credentials in
  reports (only the env-var name `SETTLEMENT_GATEWAY_KEY` is referenced).

## Limits and incidents

- Live `returned` model id is unknowable at record-assembly time (per-request
  field; gateway files untouched as required) — recorded null with a pointer
  to receipt `model_meta`. Fixture `returned` is `scripted` by construction.
- Tree hash covers tracked diffs + status paths; untracked file contents are
  named, not hashed.
- INCIDENT (stash race, shared repo): a `git stash` in this worktree collided
  on the repo-global stash ref with lane ENG-INVA (`/tmp/asv2-eng-inva`,
  branch `codex/eng-inva`). My 4 files were recovered byte-identical from
  unreachable stash commit `3fb0ffb` (verified: 307+/34-, tests re-green);
  their `store.py` edit (unrelated receipt/reconcile work) popped into my
  tree and was reverted (`git checkout HEAD -- src/settlement/store.py`) —
  my branch contains none of it. ENG-INVA's tree currently holds
  byte-identical copies of my 4 ENG-PROV files (verified with `cmp`) plus
  their own `store.py` change and `tests/test_inva_recovery.py`; their lane
  should drop my 4 files and re-check their `store.py` state (recoverable
  from unreachable `065327c` if needed). Recommendation: lanes must never
  `git stash` in shared-repo worktrees; use `git commit` or patches instead.
