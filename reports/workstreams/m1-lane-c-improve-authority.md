# M1 Lane C — improve channel authority and round-result ownership

Lane C of the M1 batch, on branch `wt/lane-c` from `a687259`. Owned scope was
`experiments/ad01/improve_channel.py`, `experiments/ad01/channel_controls.py`
and this file. Nothing else was edited.

## What shipped

| Change | Location | Lines |
|---|---|---|
| Delete `ceiling_over_inputs` | was `improve_channel.py:1108` | −22 |
| Refuse `authority=None` on an owned store | `drive_improve_round`, now `:2131-2135` | +20 docstring, +4 code |
| Ask the store's validator before the round result reaches disk | `drive_improve_round`, now `:2327-2340` | +11 |
| Drop the duplicated `granted = authority` | now `:2169` | −1 |

`channel_controls.py` needed no change. Its one executor-reaching call already
carries `authority={"dsn": ..., "allocation_id": ...}` and no retired keyword.

## The authority requirement, and what it is keyed on

The failure is not that `authority` defaults to `None`. It is that "the caller
supplied nothing" and "the caller supplied a disposable store" were the same
value at the point where the difference matters. A required argument would fix
the omission and nothing else: `run_live_improve_round` would then have to
*write* `authority=None`, which is the same silent substitution with a
TypeError wrapped around it.

The distinction the round actually needs is not "did the caller answer the
question" but "does this store name an owner whose investigation the receipts
would have to reach". So the guard keys on `store.identity`, which is
`None` for a fixture store and a `StoreIdentity` for any store opened through
`ensure_live_store(dsn=..., investigation_id=...)`. One property, read at one
place, replaces a default that had to be interpreted at every call site.

A nameless store still gets `_disposable_authority`. That default is sound
there: such a store records no durable owner, so a receipt that does not
outlive the round contradicts nothing. `_disposable_authority` is untouched and
`test_inv_a8_improve_authority.py:231-247` still holds, verified by parsing
`drive_improve_round`'s AST for the name (still present, checked below).

## Lane B must implement this

`live_construct.py` is Lane B's. The refusal below is inert until Lane B
supplies real authority, and the production live path is broken until then.
This is deliberate: a silent disposable store on an owned store is the defect,
and the whole point is that the defect can no longer be reached quietly.

**Spec, at the commit this lane was written against.**

1. `live_construct.py:1216-1217` — add a keyword to `run_live_improve_round`:
   `authority: dict | None = None`. It must stay optional, because
   `tests/test_live_integration.py:427,441,459` and `tests/test_r123_gates.py:107,115`
   call it with four positional arguments on nameless fixture stores, and the
   nameless path is the fixture boundary this module already documents.

2. `live_construct.py:1222-1225` — forward it. The call becomes:
   ```python
   return _channel.drive_improve_round(
       store, task, package=dict(package), round_no=int(round_no),
       arm=arm, admit_probes=True, authority=authority)
   ```

3. `live_construct.py:1378-1380` — `bind_live_revision` already holds
   `dsn` and `investigation_id` in its signature (`:1447-1449` at the time of
   reading). Pass `authority=...` there. The store is `restarted`, opened by
   `restart_store(str(store_path), dsn=dsn, investigation_id=investigation_id)`,
   so this round is on an owned store and **will** refuse without the keyword.

4. `live_construct.py:1513-1514` — `live_frontier_round` likewise holds
   `dsn`/`investigation_id`. Same change. (Note: the ownership map lists
   `live_frontier_round` at `:1489` as zero-caller and slated for deletion.
   If Lane B deletes it, step 4 disappears. Check before implementing.)

5. `live_construct.py` needs a way to *construct* that authority. The mapping
   `{"dsn", "allocation_id"}` is what `_run_source` demands
   (`improve_channel.py:1795-1798`). `StoreIdentity` (Lane E's
   `frontier.py:88-91`) carries `dsn` but **no** `allocation_id`, and
   `dsn` alone is a refusal. So the allocation has to be bought.
   `settlement.authority.authorize_study(dsn, study_root, authorized=...,
   allocation_id=..., ceilings={"sandbox_calls": ...})` is the entry;
   `s09_run_isolation.study_root_for(token)` gives the root string.
   `scripts/invl02_live.py` already holds a study allocation under the name
   `"ad01-campaign-%s" % use_cid` (`:2276`) and already reads spend from it
   via `_already_spent(dsn, allocation_id)` (`:245`). The round's allocation
   should be that same study allocation, not a new one. Buying a second
   allocation for the same study would be the "second authority" the lane
   constraints forbid.

6. Which allocation id is correct is **Lane A's** call, not Lane C's.
   `scripts/invl02_live.py:_run_frontier_investigation` (`:1934`) already
   takes `dsn` and already derives `investigation_id`; it calls
   `run_live_improve_round` at `:1973` and `:1996` on
   `_live.ensure_live_store(..., dsn=dsn, investigation_id=investigation_id)`
   stores, so both of those rounds are on owned stores and both will refuse.
   Lane A owns `invl02_live.py`. Either Lane A passes the allocation down
   through `run_live_improve_round`, or Lane B's `live_construct` resolves it
   from the `dsn` it already holds. They must not both do it.

## Tests expected to go red, and why that is the correct signal

Four production-path tests drive a round on an **owned** store. Each will now
refuse, and each was measuring the defect:

- `tests/test_r123_gates.py:192` `test_r1_driver_routes_through_frontier`
- `tests/test_r123_gates.py:204,210` `test_r1_live_improver_via_doubles`
- `tests/test_invl02_causality.py:348,1042` (both reach
  `_run_frontier_investigation` with a real `dsn`)
- `tests/test_a22_mission_identity.py:218` if it reaches a full round

None of these appear in `reports/evidence/ci-baseline-37172638343.md`, so
they were green at `0ee4699` and this lane turns them red. **That is the
intent.** A green test here asserts a candidate came back, and the assertion
could not tell whether the receipts behind it survived. The refusal is the
defect becoming visible. Lane A and Lane B restore them by supplying real
authority, which is the only correct fix.

Verified as *not* affected: every other `ensure_live_store` /
`create_store` / `restart_store` call in the round-driving test files supplies
no `dsn`, so its store is nameless and the disposable default still applies.
Checked by AST over `test_binding_provenance.py`,
`test_provenance_authority.py`, `test_r123_gates.py`,
`test_s09_receipt_readback.py` and `test_live_integration.py`: 38 call sites,
all `owned=False` except none. `test_a34_quiescence.py:96` and
`test_a27_store_identity.py:179` do use owned stores with non-default grants,
and neither drives a round.

## The `round_results` append

`improve_channel.py:2330` wrote `store._doc["round_results"].append(result)`
past the class's own validation. `FrontierStore` has no round-result writer;
`frontier.py` is Lane E's, so the write cannot become a method call from here.

What could be repaired without touching Lane E's file: the entry now reaches
disk only if the store's own `_validate_round_results` accepts it. The
validator runs before `save()` and the entry is withdrawn if it refuses, so a
document the store would refuse to reopen can no longer be written by the code
that wrote it.

**What is not fixed.** The append is still an append. `frontier.py` has no
`record_round_result`, and adding one is the real repair. It is one method
beside `record_round_command` (`frontier.py:1745`), holding the append, the
digest, and the validation, so nothing outside the class can write the
projection. **Lane E should add it** while retiring the JSON store, or the
ownership migration should move the projection to SQL and delete it.

Two green tests read the projection and are preserved by keeping it:
`tests/test_frontier_atomicity.py:257` (forges a log entry, expects the reopen
to refuse) and `tests/test_m2_frontier_inherit.py:428` (reads the last entry's
candidate after a fresh-process round). Neither is in the CI baseline, so both
were green and both still are, because the projection still receives exactly
one validated entry per round.

## The nineteen source-text gates, checked

Read each cited line before editing. Only two read either of my files, and both
hold, verified by re-parsing the edited source rather than by eye.

| Gate | Reads | Result |
|---|---|---|
| `test_inv_a8_improve_authority.py:85` | `_run_source` signature | Unchanged. Untouched. |
| `test_inv_a8_improve_authority.py:170-197` | every `{_run_source, run_improve_step, run_operate_step}` call in the module | **4 before, 4 after.** Lines 236, 1882, 1906, 2197, all with `{authority, operation_id}`. Threshold is `>= 4`. |
| `test_inv_a8_improve_authority.py:231-247` | `_disposable_authority` in `drive_improve_round`'s AST | Holds. Name still in the body. |
| `test_a42_chain_demonstration.py:890` | `fresh_round`'s source text | Holds. 1 `FrontierStore(` call, opener prefix intact, `identity=`, `dsn: str \| None = None`, `investigation_id: str \| None = None` all present. |
| `test_inv_x1_call_arity.py:232` | `channel_controls.drive_record` source | Holds. `authority={` and `run_improve_step` present; `dsn=dsn` and `allocation_id=allocation_id` absent. File unmodified. |
| `test_inv_x1_call_arity.py:54,72` | `run_improve_step`/`run_operate_step` signatures and every caller's keywords | Holds. `authority` still defaults to `None`, so `_accepted_keywords` is unchanged; the only production caller (`channel_controls.py:381`) supplies it. |
| `test_c14_live_already_spent_source.py:201,207,226` | `scripts/invl02_live.py` | Not my file. Untouched. |
| `test_invl02_causality.py:854-855` | `invl02_live.run_output_live`, `_DurableBrokerOutput` | Not my file. |
| `test_r123_gates.py:181,293` | `invl02_live.run_e0`/`run_e12` | Not my file. |
| `test_json_repair.py:137` | `invl02_live.probe` | Not my file. |
| `test_ad01_r4_compare.py:95` | `scripts/ad01_r4_compare.py` | Not my file. |
| `test_experiment_contract_repair.py:71` | sha256 of `twodomain.py` | Not my file. Lane D's digest. |
| `test_c20_bound_record_claims.py:100` | fixture JSON + `channel.IMPROVE_HIGH_SOURCE` | Holds. Module constant untouched. |
| `test_invl02_route_discovery.py:62` | `live.OUTPUT_ROUTE` | Not my file. |
| `test_inv_x3_freeze_methods.py:473` | `channel_controls.build_control(role)["source"]` for four roles | Holds. `channel_controls.py` unmodified. |
| `test_a32b_bound_reason.py:67` | `trajectory._construct_policy_revision` | Not my file. Lane E's. |
| `test_r_final_freeze_and_chain.py:254` | `invl02_live` run functions | Not my file. |
| `test_twodomain_instance_agreement.py:63` | `twodomain` instance fields | Not my file. Lane D's. |

`test_a42_chain_demonstration.py:535,537,541` also names three of my
functions in a chain table (`fresh_round`, `admit_revision_under_freeze`,
`frozen_state`). All three are still defined; none was renamed.

## What could not be verified

**No test suite was run.** I did not execute pytest, WSL, or any live route, by
assignment. Every claim above is from reading code, from `ast.parse`, and from
AST and grep sweeps over the tree. Specifically unverified:

- That the four owned-path tests fail with my refusal rather than some other
  error. The refusal is the first statement in `drive_improve_round`, so it
  should precede everything, but no run confirms it.
- That `_validate_round_results` accepts every entry the round now writes.
  Read, it should: the candidate is already `validate_package`-checked via
  `stage_round_candidate` on the grant the same store carries, and the
  receipts are already `validate_evidence_record`-checked in
  `record_round_command`. Both grants in play are the default
  `{"queries": 16, "steps": 12}`. A grant smaller than a candidate's
  `authority_request` would now refuse at write time where it previously
  persisted. No such grant exists in any round-driving fixture.
- Whether `_validate_round_results` is expensive enough to matter. It is O(n)
  over historical results and now runs once per round rather than once per
  open. Not measured.
- Whether the CI baseline (measured at `0ee4699`, a tree behind this one)
  still describes this tree's reds.

## Principles applied

**Subtract before you add.** One function deleted, one duplicated assignment
deleted, one guarded by three lines rather than one threaded through every call
site.

**Repair the earliest wrong boundary.** The defect is a store that names an
owner executing against a database that does not outlive the round. The guard
is keyed on ownership, which is that boundary, not on whether a keyword
arrived.

**Model the domain.** `store.identity` already distinguishes the fixture
boundary from the owned store. Making the authority rule read that field means
the type carries the distinction instead of a default standing in for it.

**Prove it works.** Each gate was re-parsed from the edited file rather than
reasoned about, and the executor-reaching count was measured with the same AST
walk the gate uses.

## What I could not fix from this lane

Three items, all outside scope, none worked around:

1. `live_construct.py` must supply real authority (spec above). Lane B.
2. `invl02_live.py` owns the study allocation name; the two owned-path call
   sites at `:1973` and `:1996` need it. Lane A.
3. `frontier.py` should gain `record_round_result` so the append becomes a
   method. Lane E, or the migration that retires the JSON store.
