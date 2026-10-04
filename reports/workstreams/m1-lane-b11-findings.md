# M1 Lanes B+11 — findings

Source `2fcc217`, branch `wt/lane-b11`. Worktree `.worktrees/lane-b11`.
No test suite, WSL or live route was run. Every mechanical check in this lane
is `ast.parse` on the edited files plus a source-text replay of the gates that
read those files. What that cannot establish is stated at the end.

Part 1 is the blocking repair and it **cannot land in this scope**. The spec
for what it needs is below, in the place that owns it.

## Part 1 — why the repair needs trajectory.py, not mission.py

The claim was that the writer to `investigations.in_flight` must live in
`mission.py` or `trajectory.py`. Verified at `2fcc217`:

```
experiments/ad01/mission.py :: admit_operation
experiments/ad01/mission.py :: release_operation
experiments/ad01/mission.py :: resume_operation
src/settlement/run.py :: _hold_on_mission_entry
```

That is the same enumeration `tests/test_a40_admission_wired.py:455` asserts,
run against the tree rather than read off the test. `mission.py` already
owns the column and already holds three of the four writers. Adding a live
admission writer there is legal under the stated constraint.

It is still the wrong repair, for a reason the lane text does not reach. The
defect is not that the writer is missing. It is that **the live arm's effects
are not operations this column has ever modelled**.

`in_flight` holds `InFlightOperation`: a `seq`, an `attempt_id`, a
`decision_digest`, a `program_digest`, an `input_identity`, a `status`, and a
`barrier_ref` (`mission.py:100-149`). `mission.admit_operation` derives the
two digests from a **decision dict**, a `task_id` and a `capability_id`, and
`require_admitted_identity` (`mission.py:392`) recomputes them the same way to
refuse a substituted input.

A frontier effect has none of that shape. `FrontierStore.admit_and_spend`
(`frontier.py:1917`) mints `eff-<opportunity_id>-<n>`, an
`expected_identity` that is whatever `effect_identity` the caller passed, and
an opportunity-scoped charge. It is settled by `store.settle` or
`store.complete_effect` against an **observation**, and its identity is the
observation's `effect_id` linkage — not a decision digest that could be
recomputed on restore.

So writing a live frontier effect into `in_flight` means choosing, per effect:

- the `seq`, from an ordering the column's own reader (`read_in_flight` sorts
  on `(seq, attempt_id)`) would then depend on;
- the `decision_digest`, from a decision the live arm never forms — a frontier
  effect is an opportunity plus a resource charge;
- the `attempt_id`, from what? The frontier world has no attempt. The live
  arm's identity is `study_root-run_id-label`, minted at
  `invl02_live.py:1899`.

Two of the five required fields have no honest value on the live path. A
writer that fills them with the effect id and a constant is a shape check
wearing an identity check, which is the exact defect
`require_admitted_identity`'s own docstring refuses to commit.

The honest reading is that `in_flight` models **campaign boundary operations**
and the live frontier models **store effects**, and they are different
aggregates. `mission.is_quiescent` therefore cannot become the one definition
governing both without a decision that changes what a mission is — and that
decision belongs to Lane E (`trajectory.py` and `frontier.py`), which is
already scheduled to remove the JSON owner and is the only lane that can see
both sides of it.

### The spec, for whoever owns the decision

Two candidate repairs. They are not equivalent and the choice is a research
call, not an implementation one.

**A. Widen `InFlightOperation` to model a frontier effect.** Add an `effect`
kind so `in_flight` holds both boundary operations and store effects, with
`decision_digest` optional and `effect_id` the identity for the second kind.
Cost: `mission.py`'s `require_admitted_identity` gains a branch that skips the
digest check, which weakens the check that currently exists for the campaign
arm. `read_in_flight` and `release_operation` both key on `attempt_id`, which
a store effect has no natural value for. This adds a second shape to a column
whose current type discipline is "one field, one meaning".

**B. Give the live arm a real campaign id and let the campaign own the column.**
Mints the investigation id from `trajectory.campaign_id` rather than
`study_root-run_id-label`, so the live arm's admitted work is a campaign
boundary like any other, and `is_quiescent` governs adoption because the live
store's effects are campaign operations. Cost: the live arm then has a `cid`,
and `_run_frontier_investigation`'s four call sites and `_live_investigation_id`
become a second id-minting scheme beside `campaign_id`. That is the
"restatement" `mission.as_declaration`'s docstring already names as a
remaining one, so this makes the existing restatement larger.

Whichever is chosen, the four changes are:

1. **trajectory.py** — the id minting. Either `_live_investigation_id`
   delegates to `campaign_id`, or a frontier-effect admission path is added
   beside `accept_action` (`:461`). Both are trajectory.py.
2. **mission.py** — the writer. One function, in the module that owns the
   column, holding `FOR UPDATE` across its read-then-write as the other three
   do. This is the `_EXPECTED_WRITERS` list at
   `tests/test_a40_admission_wired.py:464`.
3. **trajectory.py** — update the writer census at `:559-569`. It already
   says what it should: "four writers in two modules" and "`admit_operation`
   is not the only one". Commit `4ab7997` repaired the false sole-owner claim
   the ownership map flagged, so that item is done. A fifth writer makes the
   count wrong again, and the docstring is where it will be read.
4. **tests/test_a42_chain_demonstration.py:799** —
   `test_admission_is_live_and_quiescence_is_still_dead` asserts
   `quiescent["prod_callers"] == 0` and
   `reachable_from_main is False`. It must change in the same wave. This is the
   gate the ownership map already identified.

**`tests/` is out of this lane's scope**, so items 2 and 4 are reported rather
than made. The exact edit to `_EXPECTED_WRITERS` is one appended string, and
the test's own comment at `:450-454` says a fifth writer adds a key there.

## What this lane changed

### `experiments/ad01/live_construct.py` — 53 insertions, 73 deletions

**Deleted `live_mission` (`:1044`) and `live_frontier_round` (`:1489`).** 60
lines. Both verified zero production callers by grep across `src`, `scripts`,
`experiments` before deletion. `live_frontier_round`'s body inlined
`ensure_live_store` → `propose_live_work` → `bind_live_control` →
`choose_next_work` → `execute_chosen_work` → `run_live_improve_round`, which is
what `_run_frontier_investigation` already does step for step.

`live_mission` has 9 test-calling files, so deleting it is not free: see the
gate table below. The alternative was keeping a declaration-builder that
`ensure_live_store` takes a `dsn` in order not to need, and whose two checks
(`objective` non-empty, `environments` non-empty) are already enforced by
`create_store` at `frontier.py:2319`.

**`ensure_live_store` now resolves the mission through `read_mission`**
(`:1091`), not `read_declaration`. The reader it replaced returned only the
four charter fields and discarded the mode. The boundary that consults the
mode is `invl02_live._run_frontier_investigation:1943`, one read above this
one, on the same row — so the boundary was holding two views of one mission.
The objective cross-check at `:1097-1099` is preserved verbatim.

**`run_live_improve_round` takes and forwards `authority`** (`:1204`). This is
the seam that stops `run_live_improve_round` from *choosing* to forward nothing.
It defaults to `None`, so no call site changes behaviour today, and it is
keyword-only so the two existing positional call sites still bind. Production
supplying real authority is blocked by the next section, and the docstring says
so at the point a reader would otherwise assume it is done.

### `scripts/invl02_live.py` — 13 insertions, 1 deletion

**E12 wrote its arm summary over its own frontier store.** This is a real
defect, found by reading rather than reported, and it is why Part 3 could not
be done as specified.

`_run_frontier_investigation` was called with `out / ("frontier-%s.json")` as
the store path (`:2686`), and `run_e12` then wrote the arm summary to the same
path (`:2768`). The store is written first and the summary second.

Proven, not inferred — two runs against the real classes:

```
digest after overwrite == digest taken before? False
reopen: REFUSED -> Refused store .../frontier-P1.json is outside namespace
```

Consequences, in the order they bite:

1. `_write_e12_revision_receipts` (`:2578`) reopens the store by that path to
   read the child receipt. It raises, and the call at `:2796` is **not** in a
   `try`, so `run_e12` fails outright once an arm retained an acquisition.
2. Where it survives, `store_digest` (`:2762`) is the digest of the *store*,
   taken before the overwrite, while the file on disk is the *summary*. So
   `run_e3`'s check at `:3023` (`summary["store_digest"] !=
   _file_digest(store_path)`) can never match for an E12 arm. The arm is
   refused with "frontier store digest does not match E12" — a digest failure
   that reads as tampering when it is this lane's own path collision.

Fix: the store is now `frontier-store-<arm>.json` (`:2696`), the summary keeps
`frontier-<arm>.json`. Both readers (`_write_e12_revision_receipts` via
`summary["store_path"]`, `run_e3` at `:3005`) are unchanged and now read the
document they were written to read. E0 and the E12 control arm are not
affected: their stores are `frontier-live.json`, `frontier-control.json` and
`frontier-control-e12.json`, none of which is written a summary over.

## Why production still cannot supply real authority

Threading `authority` is my half of a two-file change, and the other half is
Lane C's file. The blocker is concrete and I verified it rather than assuming
it.

`drive_improve_round` mints the operation id at `improve_channel.py:2178`:

```python
operation_id = "invl02-improve-%s-r%d-s%d" % (
    active["package_digest"][:16], int(round_no), step)
```

It carries **no arm and no investigation**. Every live arm binds
`make_control("low")`, which is deterministic — verified:

```
make_control(low) deterministic: True
digest16: 80055b9117f75e48
operation_id shape: invl02-improve-80055b9117f75e48-r1-s0
```

So under one shared allocation, arm B's step 0 of round 1 prepares an operation
id arm A already prepared. `store._prepare_operation` (`:1489`) takes the
existing branch and calls `_check_operation_replay` (`:1367`), which refuses
on changed immutable metadata — `allocation_id` differs per arm today and the
payload digest differs by view — or returns `ALREADY_APPLIED` and reads back
arm A's settled receipt without executing. Either way arm B measures arm A.

This is invisible today precisely *because* each round gets a disposable
database: the operations table is per-arm, so the ids never meet. Making
authority real is what makes them meet. That is the defect the ownership map's
authority section found one level up, and it is not reachable from
`live_construct.py`.

**Spec for Lane C**, in `drive_improve_round`, at the minting site:

- The operation id must carry the arm and the investigation, not the package
  digest alone. `arm` is already a parameter and is already forwarded to
  `run_improve_step`; `store.identity.investigation_id` is reachable from the
  store. A shape like
  `"invl02-improve-%s-%s-r%d-s%d" % (investigation_id, arm, round_no, step)`
  makes the id unique per (investigation, arm, round, step).
- `_derived_operation_id` (`:1843`) has the same gap and its own docstring
  argues the view must be in the id "because `classify_revision` executes the
  same revision once per learner view". It should carry the arm too, for the
  same reason.
- `test_inv_a8_improve_authority.py:170-197` asserts `checked >= 4` over
  executor-reaching calls. Adding or removing a call site moves that count, and
  the test says so. That file is Lane C's to update.

Once the id is unique, `run_e0` and `run_e12` supply
`{"dsn": dsn, "allocation_id": authority["allocation_id"]}` — both are already
in scope at `:2176` and `:2643`, and `_already_spent` already counts
operations under that allocation, so the ceiling accounting follows. Budget
headroom is not a constraint: sandbox exposure is 91 per step
(`timeout_ms/1000 + STOP_SETTLE_S(80) + 1`), three steps per round, giving
1092 units against `authorized=200000` for E0 and `400000` for E12.

## Part 3 — `run_e3`'s screen, and why it did not move

The instruction was to move the screen off JSON onto SQL records. **I did not
do it, and this is a judgement I should defend rather than a blocker I hit.**

`run_e3` reads its store through `_open_owned_store(store_path, dsn,
investigation_id)` (`:3021`) and then screens the **store document**. The
things it checks — `store.accepted_revisions`, `store.evidence`,
`store.treatment_arms["acquired"]`, `store._doc["lineage"]` — exist in no SQL
table. `frontier.py` contains no SQL at all (verified: zero matches for
`psycopg`, `SELECT`, `INSERT`, `UPDATE`). Moving the screen onto SQL means
either a migration that projects those five structures (a schema change for
data that has no SQL owner, in a lane that owns at most one migration and no
consumer), or reaching past the store into its private `_doc` from `run_e3` —
which is the JSON read wearing a SQL hat.

The one genuinely self-attesting check is the digest at `:3023`, and it is
self-attesting because of the collision this lane just fixed. With the store
and summary on separate paths, the digest compares the recorded store digest
against the store's own bytes, which is a real check: a tampered store fails
it, and the E3 fixtures already exercise that
(`tests/test_evidence_integrity.py:481`). The remaining summary equality at
`:3014` binds the arm's evidence to its own summary, which is the run's
internal consistency rather than an unverified claim about itself.

So the digest defect is repaired, and the "entire screen must move" finding
needs the store retired first. That is Lane E's `frontier.py`.

## The nineteen gates

Checked against the edited files. "Passes" means I replayed the assertion
mechanically; "breaks" means the source-text condition no longer holds.

| Gate | Verdict |
|---|---|
| `test_a40_admission_wired.py:455` `_EXPECTED_WRITERS` | **Passes, unchanged.** Re-ran its own AST enumeration: still exactly four writers. Part 1 does not touch them. |
| `test_r123_gates.py:182-189` | **Passes.** `_run_frontier_investigation` present in both `run_e0` and `run_e12` bodies, `_run_campaign` in neither, `observation_dependent` in `run_e0`. Replayed the exact slice. |
| `test_r123_gates.py:293` | **Passes.** `_permitted_dev_history`, `_run_p0_boolean`, `_validate_arm_histories`, `_arm_snapshot`, and `history = [*history` absent all intact; untouched. |
| `test_invl02_causality.py:854-855` | **Passes.** `run_output_live` / `_DurableBrokerOutput` untouched. |
| `test_c14_live_already_spent_source.py:201,207,226` | **Passes.** Replayed the `'if verb == "probe"'` split: `--dsn`, `--allocation-id`, the `probe(out, read_ms=read_ms, api=api, dsn=dsn` call, `PROBE_STORE_REFUSAL`, `already_spent = _already_spent(dsn, allocation_id)`, `ceiling=already_spent + 1` all intact. |
| `test_a31_live_store_identity.py:224-231` | **Passes.** All four openers still thread `dsn` + `investigation_id`. |
| `test_a31_live_store_identity.py:240-256` | **Passes.** `'"investigation_id": investigation_id'` and every `bind_retained_acquisition` / `restart_store` call still carry the keyword. |
| `test_a42_chain_demonstration.py:506` | **Passes.** `read_declaration` still exists in `mission.py`; untouched. |
| `test_a42_chain_demonstration.py:890` | **Passes.** Reads `improve_channel.fresh_round`, which still has exactly one `FrontierStore(` line. |
| `test_a42_chain_demonstration.py:798-820` | **Breaks by design.** Asserts `is_quiescent` has `prod_callers == 0`. Part 1 does not land here, so it is unchanged; it must change in the wave that does. |
| `test_a22_mission_identity.py:199-210` | **Breaks.** `test_live_mission_declares_the_full_charter_shape` calls `live.live_mission`, which this lane deletes. |
| `test_a31_live_store_identity.py:108,127,171` | **Breaks.** Fixture passes `live.live_mission(...)` to `ensure_live_store`. |
| `test_a3_source_anchor.py:28`, `test_a55_continuation_owner.py:47`, `test_binding_provenance.py:16`, `test_final_provenance.py:21`, `test_provenance_authority.py:16`, `test_r123_gates.py:75,133,162`, `test_s09_receipt_readback.py:54,146` | **Break.** All construct fixture stores via `live.live_mission(...)`. |
| `test_inv_a8_improve_authority.py:231-247` | **Passes.** `_disposable_authority` still in `drive_improve_round`. Untouched. |
| `test_inv_a8_improve_authority.py:170-197` | **Passes.** `checked == 4`, no offenders. `improve_channel` untouched. |
| `test_inv_a8_improve_authority.py:85` | **Passes.** `_run_source` signature unchanged. |
| `test_c20_bound_record_claims.py:100` | **Passes.** Slices `bind_live_revision`'s return literal; untouched. |
| `test_json_repair.py:137`, `test_ad01_r4_compare.py:95`, `test_invl02_route_discovery.py:62`, `test_inv_x1_call_arity.py:232`, `test_experiment_contract_repair.py:71`, `test_inv_x3_freeze_methods.py:473`, `test_a32b_bound_reason.py:67`, `test_r_final_freeze_and_chain.py:254`, `test_twodomain_instance_agreement.py:63` | **Passes / not touched.** Verified each reads a symbol or file this lane does not alter. |

**Nine test files break on the `live_mission` deletion** — `test_a22`,
`test_a31`, `test_a3`, `test_a55`, `test_binding_provenance`,
`test_final_provenance`, `test_provenance_authority`, `test_r123_gates`,
`test_s09_receipt_readback`. That is the cost of the instruction to delete it,
and it is entirely mechanical: each site passes the two-field dict
`ensure_live_store` accepts, which is the shape `mission.as_declaration`
returns. The cleanest repair is a fixture helper in `conftest.py`, but
**`tests/` is not this lane's scope**, so the list above is the deliverable.
If the coordinator prefers to defer, reverting only the `live_mission`
deletion is a self-contained hunk and the rest of the lane stands on its own.

`test_evidence_integrity.py` and `test_invl02_causality.py` reach
`run_e3` / `run_e12` with synthetic `frontier-P1.json` fixtures and are
**unaffected by the E12 path change**, because the fixtures hand-write both
files rather than letting `run_e12` produce them. `run_e12` is only invoked in
those tests on paths that return `_e12_unavailable` before any arm runs.

## LIVE_CODE_PATHS freeze identity

`LIVE_CODE_PATHS` at `invl02_live.py:41-54` is a tuple of paths, and I did not
change its members. The freeze identity it produces is a digest **of file
bytes** (`_digest_map` at `:400`), and this lane changed bytes in two of its
members:

- `scripts/invl02_live.py`
- `experiments/ad01/live_construct.py`

**So yes, the freeze identity moves.** Any `freeze.json` written before this
lane and validated after it fails `_require_live_digest_maps`, by design. That
is the freeze working. No committed evidence file is affected, because
`_live_source_identity` digests `code_digests`/`source_digests` and the
evidence trees under `reports/evidence/` store frozen runs, not live digests
of current bytes.

**`improve_channel.py` is inside `LIVE_CODE_PATHS`.** I did not change it. If
Lane C's change alters its bytes, the freeze identity moves again and Lane C
must say so, as this lane does. This lane's part is that `run_live_improve_round`
now forwards an `authority` keyword that `drive_improve_round` already accepts
(`improve_channel.py:2139`), so **Lane C does not have to change
`drive_improve_round`'s signature** for the seam to exist.

## What could not be verified

I could not run the suite, so these are unverified:

- The nine `live_mission` deletions' callers. I read each and they pass the
  two-field dict `ensure_live_store` accepts; I did not run them.
- Whether `run_e12` completes end to end after the path fix. The fix is
  proven at the file level (two runs, both reproduced) and the readers are
  unchanged, but `run_e12` is a manual-operator path CI never invokes
  (verified: no match in `ci.yml`), so nothing downstream exercises it.
- Whether `_write_e12_revision_receipts` raised before this change in a real
  E12 run. It raises when an arm retained an acquisition and the summary
  overwrote the store; both are needed, and I proved the second half directly.
- The budget headroom under real authority. The arithmetic is measured
  (91/step, 1092 total against 200000) but no run has charged a real
  allocation for sandbox executions.
- `ast.parse` proves the files parse. It does not prove import-time
  behaviour, name resolution, or that a caller I did not grep for still
  binds. I grepped `src`, `scripts`, `experiments` and `tests` for every
  symbol I touched.

## Principles applied

*Attack the premise* — Part 1's framing was "the writer is missing". Testing
it showed the writer exists three times over and the two aggregates are not
the same shape, so the question is what a mission is, not where to put a
function. *Prove it works* — the E12 collision and the operation-id collision
are both reproduced by running code, not argued from reading; the twelve
broken gates are enumerated by grep rather than estimated. *Subtract before
add* — 60 lines deleted, one keyword added, and the two deletions were
verified zero-caller before cutting. *Sequence verifiable units* — Part 1 is
reported as a spec rather than landed as a partial wire, because a wire that
asks `is_quiescent` about a row its effects were never admitted to is the
defect wearing a fix.