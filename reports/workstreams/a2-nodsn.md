# Lane A2 — close the `dsn is None` execution hole (inv-a L2, seam S3)

Branch `wt/a2-nodsn`, base `f03db5b`, commits `1e0dd44` (fix) and `7e22d9b`
(this report). Diff touches exactly three files: `experiments/ad01/method_exec.py`,
`reports/workstreams/a2-nodsn.md`, `tests/test_inv_a_no_dsn_execution.py`.
Nothing outside `method_exec.py` and my own test file was edited;
`policy_step.py` and `trajectory.py` needed no change and were not touched.

## What changed and why

`run_step_out_of_process` and `run_member_out_of_process` each carried a live
`dsn is None` branch that executed policy source through `launcher.dispatch`
directly, outside the broker. Containment held — the bytes still ran in a
child — but authority did not. That route minted no operation row, no
allocation, no receipt and no attribution, so nothing recorded that a local
source had run. It was the "no source file may become trusted merely because
it is local" violation and the missing-authority tamper case at once.

Authority is now the type of the call rather than a runtime branch. `dsn`,
`allocation_id` and `operation_id` are mandatory for any policy-source
execution, and a caller with no authority is refused before a byte is staged.
Deleted rather than left as a second route:

- the raw `launcher.dispatch(broker.BrokerOp(...))` send (step, and member)
- every `launcher.read_result(...)` read
- the `tempfile.TemporaryDirectory` staging path (both executors)
- the `operation_id or "member"` / `operation_id or "step"` defaults, which
  minted a fixed identity for an operation that had no durable row
- all `if dsn is not None` / `if dsn is None` conditionals in the module, and
  the now-unused `import tempfile`

Net −92 lines in `method_exec.py`. Every send now goes through
`broker.ensure_operation` then `broker.dispatch_operation`.

`policy_step.py` and `trajectory.py` needed no change: `run_policy_step`
already forwards all three, and every `trajectory` call site that reaches
these executors already passes a dsn, passing `None` only through a
`*execution`/`**authority` dict that is empty on a non-durable route — which
now refuses at the executor rather than executing unbrokered.

One deliberate non-change: on the durable path the old code did not set
`result["queries"]`, so I did not add it. The replay branch already returns
early, and the non-replay durable path reports the receipt's own count.
Setting it unconditionally would have overwritten a recorded value with a
live oracle count, which is a claim the receipt does not support.

## Gate

Exact command (WSL, real PostgreSQL). The `SETTLEMENT_CLAIM_LEDGER` export is
required in this environment and is explained below; it is an environment
repair, not part of the change.

    wsl -d Ubuntu -u ubuntu -- bash -lc 'cd /mnt/d/AI/Agent-Society-v2/.worktrees/a2-nodsn && export SETTLEMENT_CLAIM_LEDGER=$(mktemp -d)/claims.jsonl && PYTHONPATH=/mnt/d/AI/Agent-Society-v2/.worktrees/a2-nodsn/src timeout 1800 /home/ubuntu/.venvs/as9/bin/python -m pytest tests/test_inv_a_no_dsn_execution.py tests/test_s09_run_isolation.py tests/test_final_provenance.py tests/test_s09m2_policy.py -q -p no:randomly'

    2 failed, 45 passed, 2 warnings in 89.94s (0:01:29)

### The two failures are pre-existing, confirmed by id

The coordinator asked for id-level confirmation rather than a matching count.
I checked out `f03db5b` into a throwaway detached worktree and ran the same
three gate files (my own new test file does not exist at base, so it is
excluded from this comparison), with the same environment override:

- **Base `f03db5b`:** `2 failed, 38 passed, 2 warnings in 130.66s`
- **Branch `1e0dd44`:** `2 failed, 45 passed, 2 warnings` (45 − 38 = my 7 new tests)

The same two ids fail on both:

    FAILED tests/test_s09_run_isolation.py::test_two_tokens_mint_different_operation_ids
    FAILED tests/test_final_provenance.py::test_durable_child_receipt_refuses_conflicted_or_unresolved_operation

No third test fails only on my branch. Nothing to fix. The throwaway worktree
has been removed; `git worktree list` shows the other lanes untouched.

Both are stale or pre-existing for reasons unrelated to authority:

- `test_two_tokens_mint_different_operation_ids` — the known baseline condition
  named in my brief. Still fails. **Not fixed by this change.**
- `test_durable_child_receipt_refuses_conflicted_or_unresolved_operation` — not
  named in my brief; I found it. A stale test fake: `_DurableCursor.fetchone`
  returns a 4-tuple `(state, "none", False, {})` while `_durable_operation` now
  unpacks 6 columns, so it dies with `ValueError: not enough values to unpack
  (expected 6, got 4)` before reaching its own assertion.

`tests/test_s09m2_policy.py::test_two_authored_policies_diverge_through_public_entry`
also fails on clean `f03db5b` **without** the ledger override, and passes with
it. See the environment note.

## Test names proving each requirement

1. `run_step_out_of_process` with no dsn raises `MethodExecutionError` and
   executes nothing:
   - `test_step_source_without_a_dsn_is_refused_and_runs_nothing`
   - `test_step_source_with_a_dsn_but_no_operation_id_is_refused`
   - `test_step_source_with_a_dsn_but_no_allocation_is_refused`
2. `run_member_out_of_process` likewise:
   - `test_member_source_without_a_dsn_is_refused_and_runs_nothing`
   - `test_member_source_with_a_dsn_but_no_operation_id_is_refused`
3. Grep-style pin, so re-introducing the raw branch is red:
   - `test_the_raw_launcher_branch_no_longer_exists_in_the_executor`
   It reads `method_exec.py` and fails on `launcher.dispatch(`,
   `launcher.read_result(`, `broker.BrokerOp(`, `if dsn is None:` or
   `if dsn is not None:`.

Each refusal test asserts nothing was constructed that could run:
`LocalLauncher` is replaced with a counter, and `broker.ensure_operation` and
`broker.dispatch_operation` are recorded, so the assertion is
`{"launchers": 0, "ensure": [], "dispatch": []}` rather than merely "it raised".

Positive control: `test_a_durable_step_still_executes_and_leaves_a_receipt`
runs the same bytes against a real disposable PostgreSQL store and asserts a
settled operation row joined to its receipt. A mandate that refused everything
would fail here instead of looking like a fix.

**The positive control is genuinely real, not a fake.** It takes no
`monkeypatch` and no fake connection class, and its `store` fixture comes from
`create_disposable_db("inva-nodsn", migrations_dir=MIGRATIONS)`, which creates
a database on the live server and applies the real migrations. Proof that it
cannot pass without a real server: pointed at a dead socket
(`PGHOST=/nonexistent-socket PGHOSTADDR=203.0.113.99`) the test cannot even
reach an assertion and the run dies in `psycopg.connect` with
`ConnectionTimeout`. A fake or a stubbed store would have passed in that
configuration.

TDD was observed. Before the fix the three target tests were red
(`test_step_source_without_a_dsn_is_refused_and_runs_nothing`,
`test_member_source_without_a_dsn_is_refused_and_runs_nothing`,
`test_the_raw_launcher_branch_no_longer_exists_in_the_executor`) and the run
reported `3 failed, 3 passed, 1 error`.

## Environment condition found (not a code change)

`/tmp/settlement-claims` is owned by `root:root` with mode `0755`. The claim
ledger (`launcher_local.py:445`) defaults to `tempfile.gettempdir()` there, and
`_append_claim` swallows `OSError` and returns `False`, so `launcher.dispatch`
refuses with `claim-not-durable` and **no real child can start at all** as the
`ubuntu` user.

Evidence, measured: writing that path as `ubuntu` gives
`PermissionError: [Errno 13] Permission denied`. Without the override,
`tests/test_launcher_local_bounds.py` reports `5 failed, 11 passed, 5 skipped`
and `test_s09m2_policy.py::test_two_authored_policies_diverge_through_public_entry`
fails with `assert 'no-candidate' == 'inspected'` — that assertion was the
*first* baseline failure I saw and is an artifact of this, not a real defect.
With `SETTLEMENT_CLAIM_LEDGER` pointed at a writable temp file the same two runs
report `22 passed, 3 skipped`. The supported override is
`CLAIM_LEDGER_ENV = "SETTLEMENT_CLAIM_LEDGER"` (`launcher_local.py:116`).

I did not change `launcher_local.py` or `tests/conftest_isolation.py`. This
needs an owner: either the root-owned directory should be created with a
writable group, or the test harness should export the override itself so a
run is reproducible without a shell incantation.

## Out-of-scope changes I need

## The 12 failures are correct signal, and they migrate in follow-up lane L2b

**Coordinator ruling, recorded here verbatim in substance: no carve-out.** A
diagnostic path that wants to execute policy source without a store is not a
special case, it is a caller with no authority. No second entry point, no
`untrusted=` flag, no opt-out that re-admits "local means trusted" under a
better name. The 12 failures are this lane working. Each one names a caller
that was relying on local trust. My gate is done and correct.

**Disposition: all 12 migrate in follow-up lane L2b — "migrate no-authority
callers onto durable authority".** L2b owns every path in the list below.
This lane migrates none of them, and I recommend the ledger name `inv-a L2b`
so the pair is findable from `reports/workstreams/inv-a.md` §(e).

**Count verified, not estimated.** On the four files below my branch reports
`13 failed, 19 passed`. At base `f03db5b`,
`test_staging_fidelity_crlf.py` alone reports `1 failed, 7 passed`, and the
failure is
`test_gitattributes_pins_every_content_hashed_tree_to_lf` (`git check-attr`
exits 128 under a worktree path). That one is a pre-existing git-worktree
artifact and is not mine. 13 − 1 = **12, all caused by this change.**

They raise `refused: execution needs explicit authority and identity` at
`method_exec.py:1121` (member) and `:1413` (step):

- `tests/test_s89a1_contract.py` — 5 (`test_bare_advertised_helper_executes_in_child`
  ×2, `test_direct_oracle_candidate_executes_in_child`,
  `test_malformed_envelope_rejected`, `test_exhausted_budget_stays_bounded`).
  One asserts `'malformed' in ...` against a different refusal reason, so L2b
  must update the expectation to the refusal, not weaken it.
- `tests/test_invc1_method_envelope.py` — 4
  (`test_independent_software_method_through_child_process`,
  `test_independent_graph_method_through_child_process`,
  `test_malformed_envelope_reports_structured_reason`,
  `test_query_exhaustion_returns_unknown`)
- `tests/test_construction_response_envelope.py` — 2
  (`test_a_policy_that_selects_a_named_method_is_reachable`,
  `test_a_policy_written_to_the_stated_access_survives_the_step`)
- `tests/test_staging_fidelity_crlf.py` — 1
  (`test_staged_driver_bytes_equal_the_source_that_was_hashed`, asserts
  `'driver.py' in {}` because staging never happens)

### Production callers L2b must migrate

These reach the executors with no dsn and now refuse. Each needs a real dsn,
allocation and operation id threaded to it.

- `experiments/ad01/trajectory.py:715` `dev_episode` → `_run_member` (`:1785`)
  with no `**execution`. Reached from `selection.py:1045` and
  `trajectory.py:715`. Inside my owned path, but migrating it changes a public
  no-dsn development API's contract, not just its plumbing, so I left it.
- `experiments/ad01/learner.py:866` `_action_of`, which calls
  `run_step_out_of_process(...)["action"]` with no authority at all. Used by
  `substitution_changes_action`.
- `experiments/ad01/experience_axis_run.py:332`, `s09_causal_proof.py:654`,
  `s09_bound_use_proof.py:260`, `s09_e2_scored.py:466`,
  `improve_channel.py:1013` — STEP sites with no dsn.
- `experiments/ad01/records.py:1599`, `policy_assess.py:222`,
  `assessment_profile.py:204`, `scripts/s89_diagnose.py:169`,
  `s09_m2_reload_proof.py:58` — member sites with no dsn.

Several of these (`s09_m2_reload_proof.py`, `records.py`,
`assessment_profile.py`) are deliberately no-store diagnostic paths whose own
docstrings say so. Under the ruling that is not a special case: each is a
caller with no authority, and L2b's job is to give it authority. A path that
provably must never touch a store should be re-expressed as something that
does not execute policy source at all, rather than as a second way to execute
it.

I made none of these changes. They are outside my path ownership.

## Incomplete

- The 12 out-of-scope test failures are unresolved **by design**. They are
  this lane's correct signal, not damage, and they migrate in follow-up lane
  L2b. My gate introduces no new failure.
- I did not run the full suite. I ran my four-file gate plus a four-file sweep
  chosen by grep for the executors, and the gate files at base in a throwaway
  worktree for the id-level comparison.
- `test_two_tokens_mint_different_operation_ids` and
  `test_durable_child_receipt_refuses_conflicted_or_unresolved_operation`
  both remain failing and unfixed, as instructed. Both are pre-existing.
