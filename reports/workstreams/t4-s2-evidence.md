# T4 S2 artifacts/evidence/continuity — task report

- Base: `8a435ca` (branch `codex/task-s2-evidence` start, per assignment).
- Tip: this commit (see `git log` on the branch).
- Worktree: `/home/ubuntu/AI/Agent-Society-v2-s2-evidence` only. No other checkout touched.

## Owned paths (only these)

- `migrations/0002_s2_evidence.sql` (one new migration; only S2 tables)
- `src/settlement/artifacts.py` (new)
- `src/settlement/evidence.py` (new)
- `src/settlement/context.py` (new)
- `tests/test_s2_artifacts.py`, `tests/test_s2_evidence.py`, `tests/test_s2_context.py` (new)

Shared contracts untouched. No contract change requests.

## Outcomes

- `uv run pytest`: **92 passed** against real PostgreSQL
  (`settlement_t2evidence`, local socket) + real filesystem (pytest `tmp_path`).
- ART-1: staging validates size caps, manifest shape, relative paths only
  (absolute/`..`/empty segments rejected), no symlinks/hardlinks/unexpected
  types, per-file digests through `O_NOFOLLOW` handles; archive unpack runs
  only via the `local-process` profile (`tar` subprocess, never in-process).
- ART-2: publish fsyncs bytes at the content-addressed path before the
  `store.transact` availability commit; `reconcile_staging` registers a
  crash-orphan whose bytes match a staging receipt and reclaims the rest.
- ART-3: references counted under the control lock; retirement marks
  `retired` before any removal; GC re-verifies protection + publication and
  claims the purge row conditionally before unlinking, so a racing reference
  lands in `kept`; missing/corrupted protected bytes flip availability to
  `invalid`, bump `evidence_epoch`, and refuse dependent use.
- ART-4: per-scope working-set/archive budgets refuse over-quota staging;
  model-proposed quota cuts below protected bytes are refused; GC keeps
  load-bearing artifacts (referenced by a live derivation of a supported
  claim) and a digest alone is never reported as available (bytes re-hashed).
- Evidence: grouped premises — retraction kills only groups containing the
  premise; multi-group derivations and alternative derivations preserve
  support; last-route death flips the obligation. Relation kinds are distinct
  (`required-support`, `opposition`, `background`, `attribution`,
  `equivalence`). `defeat` blocks admissibility, plain `opposition` does not.
  Interpretive text yields an unauthenticated note that cannot support a
  claim; receipts carry source identity + conditions. Cycle-safe traversal.
- Concurrency: every retraction/defeat calls `store.register_evidence_change`;
  `check_use` rejects a stale `evidence_epoch` (`missing_evidence`) and
  recomputes before consequential use. Tested racing release/fulfillment
  order: `fulfill_investigation` with a pre-retraction epoch is refused while
  a fresh-epoch fulfill commits.
- RUN-5/IF-3: `build_context` returns a versioned view with decision, kept
  sources, transforms, governing refs and limitations; missing mandatory keys
  or withheld sources produce a staged/narrowed view, never a silent drop.
  Access labels are enforced by SQL predicates (`scoped_claims`,
  `scoped_artifacts`); hidden material is invisible to `candidate` scope and
  visible to `evaluator`.
- RUN-2: continuation docs (composition version, position, completed refs,
  unresolved op ids, obligations, next decision) are stored as immutable
  files, registered as artifacts, recorded in `continuation_docs`, and
  installed via the attempt's `continuation_ref` in one transition.
  `resume_package` assembles continuation + `restart_reconciliation` pending
  ops + observations + admissibility snapshot. Fresh-worker test passes:
  worker B (new generation, no shared memory) sees A's pending op, preserved
  observations, and the intervening retraction reflected in support.

## Limitations / notes for reviewers

- Staging and final artifact bytes live under pytest `tmp_path` roots passed
  in by the caller; production wiring of `ARTIFACT_ROOT`/`STAGING_ROOT`
  (config + CLI flags) is left to the integrator.
- `observations.receipt_id` derives from the command request id; duplicate
  request ids replay idempotently through `store.transact` as usual.
- Admissibility "exact version match" is enforced as exact
  procedure/version strings on warrants plus epoch-validated recompute; there
  is no separate procedure registry — T5 may add one in `0003` if trials need
  it.
- Attempt deadlines and lease expiry are T3/T6 policy (unchanged semantics).

## Public API for T5 (all take `(dsn, cmd, ...)` for mutating calls)

- `artifacts.stage_package(dsn|None, staging_root, *, manifest, files,
  scope="", access_label, format, version, dependencies)` → receipt dict
  (includes `digest`, `size`, `staging_dir`).
- `artifacts.publish_package(dsn, cmd, artifacts_root, receipt)` →
  `CommandResult` (`data.digest`).
- `artifacts.reconcile_staging(dsn, staging_root, artifacts_root)` →
  `{registered, reclaimed}`; `collect_garbage(dsn, artifacts_root)` →
  `{removed, kept}`.
- `artifacts.add_reference / remove_reference(dsn, cmd, digest, holder_kind,
  holder_id)`; holder kinds: `evidence|release|attempt|checkpoint|continuation`.
- `artifacts.retire_artifact(dsn, cmd, digest)`;
  `verify_bytes(dsn, artifacts_root, digest)` → `{ok, reason?}`;
  `artifact_available(dsn, artifacts_root, digest)` → bool.
- `artifacts.set_retention_budget / propose_retention_change(dsn, cmd, scope,
  quota_bytes, ...)`; `scope_usage(dsn, scope)`; `scoped_artifacts(dsn, scope)`.
- `evidence.register_observation(dsn, cmd, attempt_id, content,
  source_identity="", conditions=None)` → `data.receipt_id/authenticated`
  (also mirrors into attempt observations).
- `evidence.propose_claim(dsn, cmd, claim_id, proposition, scope,
  assumptions, access_label)`; `admit_warrant(dsn, cmd, derivation_id,
  claim_id, procedure, proc_version, premise_groups, scope, assumptions,
  result)` where `premise_groups: list[list[(ref, kind)]]`,
  kind in `claim|observation|artifact`.
- `evidence.register_opposition(dsn, cmd, opposition_id, claim_id, kind,
  body)` (kind `opposition|defeat`); `retract(dsn, cmd, target_ref, reason)`;
  `record_relation(dsn, cmd, src_ref, dst_ref, kind, detail)`.
- `evidence.current_support(dsn, claim_id, artifacts_root=None)` →
  `{supported, version, epoch, derivations}`;
  `check_use(dsn, claim_id, evidence_epoch, artifacts_root=None)` (raises
  `MissingEvidence` when stale/unsupported); `scoped_claims(dsn, scope)`;
  `claim_support_view(dsn, claim_id)`.
- `context.build_context(dsn, cmd, decision, source_refs, transforms,
  governing_refs, limitations, caller_scope, mandatory)` → `data.view_id,
  staged, missing, withheld, narrowed_decision?`; source refs use
  `{claim_id?/digest?}` keys.
- `context.save_continuation(dsn, cmd, artifacts_root, investigation_id,
  attempt_id, composition_version, position, completed_refs, unresolved_ops,
  obligations, next_decision, ownership_generation=None)` →
  `data.continuation_id`.
- `context.resume_package(dsn, investigation_id, caller_scope="evaluator")` →
  `{continuation, live_attempts, pending_operations, observations, support,
  reconciliation}`.
