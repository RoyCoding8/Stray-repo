# INV-D3 lane note: ENTRY return envelope statement plus case B3 pin

Branch `wt/inv-d3-envelope`, base `b67ecbf` (verified before work).
Owned paths only: `experiments/ad01/construct.py` (`_prompt`
function only), `tests/test_invd3_envelope.py` (new), this note.
Untouched: all other `experiments/**`, `src/**`, `scripts/**`,
other `tests/**`, `pyproject.toml`, `uv.lock`, `reports/PLAN.md`.

The assigned review
`reviews/INVESTIGATION-01-COMPLETION-VERIFY.md` is absent on this
tip (measured `ls reviews/` plus a repo-wide grep for `INV-C4`
with zero matches), so the work below proceeds from the live
contracts and the M4 row of
`WORKER-INVESTIGATION-01-COMPLETION.md` plus `reports/workstreams/inv-c1.md`.

## INV-C4: reproduction on this tip

`fad7e7e` (INV-C1) is an ancestor of this tip, and its envelope
work is present. Measured on the unmodified tip with the shared
venv interpreter:

- `construct._prompt` output already contains the verbatim
  `entry_contract()["result_envelope"]["rule"]` string, rendered
  through `packet.render_construction_prompt`.
- A bare-candidate method (`return task`) passes `verify_member`
  and dies in the real child process with the structured
  `malformed-result-envelope` error, not `KeyError: 'candidate'`.
  No `KeyError: 'candidate'` path remains: the driver reports the
  envelope shape failure directly, and `_result` raises
  `MethodExecutionError` on malformed output.

The literal `KeyError` from the finding does not reproduce on
this tip (measured absence by code inspection of the driver plus
the child run above). The user-visible failure mode it stood for
(prompt read literally, bare candidate returned, child dies)
does reproduce, with the documented structured error.

## INV-C4: production change

`_prompt` still delegates rendering to `packet.py` (C1-owned,
untouchable in this lane) and now guarantees the envelope
statement structurally: it reads the rule verbatim from
`method_exec.entry_contract()` and appends exactly
`"\nReturn envelope: %s." % rule` only when the rendered text
does not already contain it. No paraphrase exists anywhere in
this lane. The executor stays the single source of truth.
Rendered output is byte-identical today because the packet
renderer already carries the rule, so no existing caller drifts.

## Tests: `tests/test_invd3_envelope.py`, 5 passed

- Prompt carries the verbatim envelope rule.
- Prompt restores the rule when the renderer drops it
  (monkeypatched render; failed before the fix, passes after).
- The documented envelope example (independently written
  software sweep, no reducers, no authored wrapper) runs through
  the actual child process: verdict preserved, strictly smaller,
  queries counted.
- The bare-candidate form passes `verify_member` and fails in the
  actual child with `malformed-result-envelope`.
- Case B3: real CLI `run` on fresh database `inv_d3_b3` without
  `--agenda-authorized` exits 2, stderr carries
  `explicit caller agenda authority`, and row counts are
  `{"operations": 0, "receipts": 0, "allocations": 0}`.

## Gates

- New file: 5 passed.
- Nearby `tests/test_invc1_method_envelope.py`: 7 passed,
  1 failed (`test_repair_prompt_reaches_model_request`,
  `ImportError` on `settlement.authority`). Proven pre-existing
  by rerunning it on the clean stashed tree with the identical
  failure. Cause is environmental: the shared venv resolves
  `settlement` to the main checkout, whose `src/settlement`
  lacks `authority.py` present in this worktree. Out of this
  lane's owned scope. The new B3 test is immune by construction:
  it drives the CLI in a fresh process with `PYTHONPATH`
  pointed at this worktree's `src`.
- `construct._prompt` callers rechecked: only the C1 envelope
  tests plus review probes; output-identical change.

## Hygiene

Disposable databases created in this lane: `inv_d3_b3` only,
dropped in the test's `finally` block. A probe database
`inv_d3_probe` created to check `CREATEDB` rights was dropped
immediately. Measured `pg_database`: zero `inv_d3_*` entries
remain. No secrets, endpoints, keys, or machine state in Git.
