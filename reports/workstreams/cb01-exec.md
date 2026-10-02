# Workstream cb01-exec — Representation Lane C (RPR-02/05/07)

Branch `codex/cb01-exec` from `0b323b7`. Author `Nightjar <nightjar@authors.invalid>`.
Worktree `/tmp/asv2-cb01exec` (own; `/tmp/asv2-agenda01` inspected read-only,
never written). Lane test DB `settlement_cb01exec`, real PostgreSQL 16,
host-param DSN `postgresql://ubuntu@/settlement_cb01exec?host=/var/run/postgresql`.
No live model calls, no credentials.

## Owned paths (new files only)

- `src/settlement/representation.py` (new, ~950 lines)
- `tests/test_rpr02_profile.py`, `tests/test_rpr05_runner.py`,
  `tests/test_rpr07_resume.py` (new)

No edits to `development.py`, `experiment.py`, `broker.py`, `store.py`,
`gateway.py`, `artifacts.py`, `capabilities.py`, migrations, or any other
lane paths. Seams reused read-only: `development.METHOD_ABI` (repair profile
preserved), `experiment._invoke_method` (untouched; runner implements its own
`_invoke_entry` on the same Launcher/broker pattern), `artifacts`
stage/publish/verify, `capabilities` version records, `broker`
ensure/dispatch/admit, `launcher_local.LocalLauncher`,
`experiments/agenda01/launcher.py` (receipt-via-dispatch boundary pattern).

## Chosen JSON schemas (selected once, RPR-02)

Profile `representation-01`, single version `representation-01/1`. Any other
`profile_version` is refused `unknown-version` on every action. ABI
`python <entry> <request.json> <response.json>`; entries write only the
response file and exit 0 with empty stdout.

Request (all actions): `{profile, profile_version, action,
task_id, composition_id, core_digest, adapter_digest, state, payload, budget}`.
`state` is the explicit prior core state (`null` for start/decode).
`budget` carries remaining invocations/queries/ms (advisory; enforcement is
controller-side from the database).

- encode payload `{source_task, domain_spec}`; ok result `{encoded_object,
  aux, applicability: {supported, reason}}`.
- start/advance payload `{encoded_object, feedback, limits}` (`feedback`
  `null` for start); ok result `{proposal}` plus next `state`; or
  `final` with `{final_object}` (start/advance only).
- decode payload `{proposal, source_task, aux}`; ok result
  `{candidate_source}`.
- refusal `{status: refuse, reason, detail?}` with reason in
  `unknown-version | malformed | stale-identity | oversize | unsupported`
  and `detail` bounded to 256 chars.

Response identity echo (`task_id`, `composition_id`, `core_digest`,
`adapter_digest`) is verified on every response; mismatch is
`stale-identity`. Non-JSON/undecodeable is `malformed`; either side over
64 KiB is `oversize`. Manifest: files `core.py`, `adapter.py`,
`DESCRIPTION.md` with sha256/size entries, explicit
`representation_entries: {core, adapter}`, `verify_args: ["--selftest"]`.
The entry is never inferred from file order (`resolve_entry` raises when
the named role is absent).

Trusted checker ABI (separate bytes, same boundary): `python checker.py
<candidate.json> <verdict.json>` with verdict `{verdict, measure, reason}`
in `preserved | not_preserved | invalid | unknown`. Timeout, crash, missing
output or schema violation is `unknown` (`timeout` / `checker-failure`),
never evidence of absence. Candidate docs share one shape
`{task_id, source_task, aux, candidate, role}` with `role` in
`candidate | initial | final`.

Step identities: component `rpr:<run>:<task>:<action>:<seq>` (per-action
sequences; `start` is proposal 0, advances are proposals ≥ 1, decode/check
share the proposal index), candidate queries `...:check:<seq>`, validation
(initial/final) `...:validate:<seq>`. Step/check records are extra receipts
(`rpr-step:`, `rpr-check:`, `rpr-validate:`) on the same real operations,
outcome `unknown` (records, never judgments). Retries reuse the identical
operation id; broker intent immutability plus receipt dedup make redispatch
a no-op.

Budgets per task: ≤ 16 candidate witness queries, ≤ 2 validation queries
(initial + final, additionally permitted and counted), ≤ 64 component
invocations, ≤ 120 s elapsed (anchored to the first durable operation
timestamp on resume, not process start), ≤ 2000 ms per invocation,
≤ 64 KiB per request/response/persisted state. First budget breach ends the
task `budget_exhausted` with the best verified incumbent retained.

## What was built

- Package/composition: `stage_composition` / `publish_composition` over the
  artifact envelope with `format: representation-01` and
  `dependencies: [core:<sha>, adapter:<sha>]`; `record_composition` binds a
  `capability_versions` row (`family: representation`, role source/transfer,
  core/adapter digests from actual staged bytes, protocol id);
  `check_composition` re-verifies bytes and digest bindings (drift is
  binding-invalid); `compositions_share_core` proves unchanged-core transfer
  from bytes, not labels.
- Runner: `_invoke_entry` (stage → ensure → dispatch → read → validate →
  record; resume short-circuits on the step receipt, so a fresh run
...[truncated 3074 chars]