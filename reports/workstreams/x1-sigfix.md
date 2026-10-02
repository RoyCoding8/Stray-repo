# Lane X1 — merged-tip signature repair

**Commit** `7011fad` on `wt/x1-sigfix`, forked from `3894f8c`.
**Verdict** two independent defects, same merged-tip signature, neither visible
to the lane that introduced it.

## Defect 1 — the one the brief named. Mechanical rename.

`channel_controls.drive_record` called
`run_improve_step(..., dsn=dsn, allocation_id=allocation_id)`. A8 changed the
signature to take one `authority` mapping. The merged call raised
`TypeError: run_improve_step() got an unexpected keyword argument 'dsn'`.

Read, not assumed: `authority` is a `{dsn, allocation_id}` mapping, checked at
`_execution_ledger` and again in `_run_source`. `drive_record` already held
both halves, so the repair is a fold, not a spelling change. The controls
execute under the caller's real ledger. Making them pass by removing
authority would have made all four vacuous.

Six of the nine failures went green on this alone (`20 passed`).

## Defect 2 — not named in the brief. Fixture, not code.

The remaining three failed with a different error:
`refused: durable child operation has no successful receipt`. Reading the
durable receipt showed `outcome=failure`, `TypeError: 'int' object is not
subscriptable` in the child.

The C3 and E4 view fixtures built `{"x": 2, "y": 1}` with a scalar `y`. The
incumbent step reads `exp[-1].get("y")[0]`, so a scalar cannot be indexed.
`boolean_rule.RuleSession._observed` is the source of the real shape
(`list(self._queried[x])`, a 4-bit vector) and every live observation in the
tree is a 4-list.

Before A8 the child raise was swallowed into an empty choice list and the
revision was admitted as eligible having selected nothing. A8 made execution
real, so the same bad fixture refused the whole verdict. The fixture was
never the shape it claimed.

Repaired the fixture. Did not swallow the error in the module: that would
have restored the vacuous admission and made
`test_an_admitted_revision_really_selects_evidence` pass by proving nothing.
It asserts `selected_evidence == [[2]]`, which holds only when the step
actually ran and probed.

No assertion line changed. The diff to the three test files is fixture values
only.

## The guard

`tests/test_inv_x1_call_arity.py` binds each call site's keywords to the
callee's real signature for the five shared functions. Both directions:

- a keyword the callee no longer has (C2's `dsn=`)
- a required keyword the caller omits (`authority` on `run_improve_step`)

Required-keyword enforcement is scoped to `run_improve_step` deliberately.
`run_operate_step` treats an absent authority as the disposable-store
contract and four inherited callers rely on it; a first draft flagged them
and was narrowed.

Non-vacuity, three ways:

- a planted caller with `dsn=`/`allocation_id=` is reported and both keywords
  are named
- a planted caller omitting `authority=` is reported
- the repaired call and a call passing an accepted keyword are not reported,
  so the guard cannot pass by flagging everything

Proven against a real planted file, not only synthetic AST: reverting
`channel_controls.py` to `dsn=dsn` failed
`test_no_call_site_passes_a_keyword_the_callee_rejects` **and**
`test_the_controls_pass_authority_as_one_mapping`, `2 failed, 5 passed`. Plant
removed, back to `7 passed`.

## Gate

Real PostgreSQL, WSL as `ubuntu`, claim ledger set. `3894f8c` plus this commit.

    tests/test_inv_c2_freeze.py tests/test_inv_c3_fixture_repair.py
      32 passed in 68.41s (0:01:08)

    + tests/test_s09rev_boundary.py tests/test_s09_e4_channel.py
      72 passed in 115.05s (1:55)

The 9 named failures reach zero. `"S09ISO: dropped 13 database(s)"` is normal.

## Not mine, still red

`tests/test_s09_e4_remediation.py::test_a_non_empty_evidence_set_is_what_makes_the_admission_say_it_informed`
fails identically at the pristine tip and at this commit. Verified by stashing
only that file and rerunning. Its subject is a hand-written program the C2
freeze refuses as `changes-an-unauthorised-decision`, so it belongs to the
E4 lane. Its two fixtures were repaired here for shape consistency only.

## Constraints

- No live model, no network, fixture gateway only.
- `git diff --name-only 3894f8c HEAD -- reports/evidence/` is empty.
- No test weakened, skipped or xfailed. No contract loosened.
- `improve_channel.py` not touched. `method_exec.py` not touched.
- Owned files only: `channel_controls.py` and the new guard, plus the three
  fixture files whose observation shape was wrong.
- No Monitor armed, no subagents spawned, one pytest at a time.
- Final live process count: 0.