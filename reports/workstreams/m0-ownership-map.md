# M0 — production mission ownership map

Source `0ee4699`, branch `codex/agent-society`. Measured by reading code and by
repo-local grep at that commit. Four independent read-only readers produced the
slices; their load-bearing claims were re-verified directly before this document
was written. Nothing here ran a test suite, WSL or a live route.

The architecture decision is already made (WORKER-PROMPT M0): SQL AD01 owns the
production mission. This document maps what exists so the migration can be done
without inventing a second authority.

## The map

| M0 item | Owns it today | SQL owner that should own it | Production reader exists? |
|---|---|---|---|
| private state | `FrontierStore._doc["private_state"]`, disk JSON (`frontier.py:2235`) | none | wrong owner |
| active package / version lineage | `FrontierStore._doc["active_package"]` / `["lineage"]` | `capability_versions`, `capability_releases` (`migrations/0003:1,35`) | only when a `release_id` is named (`selection.py:60,267`) |
| frontier choice | `FrontierStore._doc["opportunities"]` | `investigations.frontier` | **none** |
| pending / in-flight effects | `FrontierStore._doc["pending_effects"]` | `investigations.in_flight` (`migrations/0020:26`) | yes (`context.py:234`, `mission.py:521,561`) |
| retained-use history | in-memory `experience` dict (`trajectory.py:1596`) | `investigations.retained_use` (`migrations/0019:28`) | **none**, and no writer anywhere |
| round continuation | `FrontierStore._doc["round_journal"]` (`frontier.py:1761`) | `s09_policy_state.accepted_action` (`migrations/0017:9`) | yes (`trajectory.py:455`, `_s09_get:317`) |
| quiescence | `len(self._doc["pending_effects"]) == 0` (`frontier.py:2214`) | `jsonb_array_length(in_flight) == 0` (`mission.py:561`) | SQL predicate has **zero** production callers |

## The defect, measured

`investigations` carries six JSONB columns added by `migrations/0019:24-30`.
Five of them have **no production reader anywhere in the tree**. Verified: every
attribute access to `.frontier`, `.permitted_experience`, `.active_program`,
`.acquired_artifacts` or `.retained_use` outside `mission.py` lands in `tests/`.

The only two production readers of the mission row are `read_declaration`
(`mission.py:341`) and `read_improvement_mode` (`mission.py:353`). The first
returns only the four charter fields via `as_declaration()` (`mission.py:98-101`),
discarding all six. So the columns round-trip through the dataclass and out the
other side into a dict that throws them away.

The live path's only mission write, `scripts/invl02_live.py:1911-1930`, passes
charter plus `improvement_mode="improve"`. It never writes `frontier`,
`permitted_experience`, `active_program`, `acquired_artifacts` or `retained_use`.
Those sit at their `0019` defaults on the production arm forever.

Meanwhile every real consumer reads the JSON document instead: active program at
`live_construct.py:1180,1314,1471`, private state at `frontier.py:2235`,
retained-use history from the in-memory `experience` dict, quiescence at
`frontier.py:2214`.

This is WORKER-PROMPT M0's "summaries into SQL columns nobody consumes", now
measured rather than suspected. `retained_use` is the extreme case: it has **no
writer anywhere in the tree**, not merely no reader.

## Three contradictions in the repo's own comments

Each was verified by reading the cited lines at `0ee4699`.

**1. A false sole-owner claim.** `trajectory.py:559-561` states
"`mission.admit_operation` is the only code in the tree that writes
`investigations.in_flight`". `src/settlement/run.py:635` is a second writer, and
its own docstring at `run.py:604-607` names itself as the reintroduced defect.
Both hold `FOR UPDATE` across a read-then-write, so the lost-update hazard is
closed on both sides. The locking is correct; the claim is wrong. Repair the
claim or remove the writer, do not add a third.

**2. A stale justification for two quiescence predicates.**
`tests/test_a34_quiescence.py:241-255` argues the two predicates honestly answer
different questions because "nothing carries one to the other". That reasoning
has expired: `StoreIdentity.dsn` is now dereferenced and recorded
(`frontier.py:848-849`, `_check_identity:892-916`), and both live entry points
supply the pair (`live_construct.py:1063-1078`, `improve_channel.py:2336-2343`).
The routing field exists. The test's conclusion was true when written and is not
now.

**3. A test that pins the defect as intended.**
`tests/test_a42_chain_demonstration.py:798-820`, named
`test_admission_is_live_and_quiescence_is_still_dead`, asserts
`mission:is_quiescent` has `prod_callers == 0` and is unreachable from `main`.
M1 requires giving it a real caller. The test becomes wrong the moment M1 lands
and must change in the same wave. It is an argument for the direction, not
against it.

## What the assignment text gets wrong

Two claims in WORKER-PROMPT do not match the code. Both are ledger material, not
lanes.

**`twodomain.py` needs no migration.** M1 lists it among the paths to migrate.
It never touches `FrontierStore`: its only "frontier" occurrences are two
`mission.record_mission(frontier=...)` keyword arguments at `twodomain.py:385`
and `:470`. It already writes SQL. Stronger, it has **zero production callers**:
grep for its two public functions outside `tests/` returns nothing, and it has no
CLI, no `argparse`, no `__main__`. Its only caller is a test fixture. It cannot
carry production authority it is not given.

**`twodomain.py` does demonstrate the projection defect.** The ledger's claim at
`PROJECT-LEDGER.md:14` that it "writes projections which production does not
consume" is confirmed. The driver and the crossing write disjoint halves of the
same row, and neither writes the half the other reads.

## Already-dead code, free subtraction

These have zero production callers **today**, before any migration. Deleting
them is independent of M1 and reduces the surface a reviewer must reason about.

| Symbol | Location | Non-test refs |
|---|---|---|
| `live_mission` | `live_construct.py:1044` | 0 |
| `live_frontier_round` | `live_construct.py:1489` | 0 |
| `reviser_own_score` | `improve_channel.py:1130` | 0 |
| `ceiling_over_inputs` | `improve_channel.py:1108` | 1 (own module) |
| `FrontierStore.accept` | `frontier.py:1990` | 0 |
| `FrontierStore.replay` | `frontier.py:2178` | 0 |
| `FrontierStore.ready_events` | `frontier.py:2204` | 0 |
| `FrontierStore.check_spend` | `frontier.py:1901` | 0 |
| `FrontierStore.record_outcome` | `frontier.py:2166` | 0 |
| `FrontierStore.predict` | `frontier.py:2197` | 0 |
| `context.save_continuation` | `context.py:113` | 0 |

`create_store` and `_validate_document` must **survive** for historical replay:
several tests load `reports/evidence/invl02-r123/frontier-live.json` as frozen
evidence (`test_c20_bound_record_claims.py:32,70,89`, `test_c5_executable_bound.py:31`,
`test_c8_gate_review.py:45`).

## M1 lane split

**This split was refuted by adversarial review on 2026-10-04 and is superseded
by the section below. Do not implement the four-lane version.** The original
version named one source-text gate; there are nineteen. Two live gates
contradict Lane C's contract outright, and two files that gates read belong to
no lane. The reviewer's citations are in `reports/workstreams/m0-map-challenge.md`.

### Lane split, corrected

Five lanes. The addition is Lane E, which owns the files no other lane could
safely touch, plus `channel_controls.py`, which a gate reads and no lane owned.

| Lane | Owns | Contract |
|---|---|---|
| E | `experiments/ad01/trajectory.py`, `experiments/ad01/frontier.py` | `resume_campaign` (`:2254`) is the only production path restoring admitted work from SQL, and `frontier.py` is the store being retired. Wire `mission.is_quiescent` to the live admission and adoption path so one definition governs both, then let `FrontierStore.is_quiescent` lose its last caller and delete it. Repair or delete the false sole-owner claim at `trajectory.py:559-561`. **Lands first**: it removes the JSON owner, which is what unblocks C and B. |
| C | `experiments/ad01/improve_channel.py` | `drive_improve_round` reads its mission from the SQL entry, not `store._doc["mission"]`. Delete the direct `store._doc["round_results"]` append at `:2330` that escapes the class's own validation. Delete the dead `ceiling_over_inputs` (`:1108`). **Do not remove `_disposable_authority`**: `test_inv_a8_improve_authority.py:231-247` asserts it is present, and the reason is sound. Instead resolve the production caller — see the authority finding below. |
| B | `experiments/ad01/live_construct.py` | Wrappers resolve mission through `mission.read_mission`, not `read_declaration`. Delete `live_mission` (`:1044`) and `live_frontier_round` (`:1489`), both confirmed zero-caller. Preserve the objective cross-check at `:1104-1111`. Pass real authority from `run_live_improve_round` (`:1216`), which today forwards none. |
| A | `scripts/invl02_live.py` | The four `_run_frontier_investigation` call sites take mission state from the SQL entry. `_run_frontier_investigation` becomes a thin caller of Lane C's round API with explicit identity. `run_e3`'s eligibility screen stops self-attesting — see below. Sole owner of `LIVE_CODE_PATHS` (`:41-54`). |
| D | `experiments/ad01/twodomain.py`, `experiments/ad01/mission.py` | Give the five columns a production reader or stop writing them. Add a `retained_use` writer or drop it from `MISSION_FIELDS`. Fix the `permitted_experience` default. **Byte-digest pinned**: `test_experiment_contract_repair.py:68-74` asserts `sha256(twodomain.py bytes)`, so any edit requires accepting a digest rewrite in the same commit. |

Forced ordering, corrected: **E before C before B before A**. E removes the
JSON owner. C then stops reading it. B stops wrapping it. A stops driving it.
D is independent and runs in parallel from the start.

Two files outside this list are read by gates and were owned by nobody:
`experiments/ad01/channel_controls.py` (`test_inv_x1_call_arity.py:232` asserts
its source shape) and `src/settlement/context.py` (Lane D's column readers
belong there). Fold `channel_controls.py` into Lane C; it is an executor-
reaching file of the same shape.

**The nineteen source-coupled gates.** Every one breaks on a rename, a moved
call, or a byte change in its lane: `test_inv_a8_improve_authority.py:85,170-197,231-247`,
`test_c14_live_already_spent_source.py:201,207,226`,
`test_invl02_causality.py:854-855`, `test_r123_gates.py:181,293`,
`test_json_repair.py:137`, `test_ad01_r4_compare.py:95`,
`test_a42_chain_demonstration.py:890`, `test_experiment_contract_repair.py:71`,
`test_c20_bound_record_claims.py:100`, `test_invl02_route_discovery.py:62`,
`test_inv_x3_freeze_methods.py:473`, `test_a32b_bound_reason.py:67`,
`test_r_final_freeze_and_chain.py:254`,
`test_twodomain_instance_agreement.py:63`, `test_inv_x1_call_arity.py:232`.

## The authority defect, which is not a cleanup item

The reviewer's most important finding, verified by me.

**The entire production live path executes with `authority=None` against a
database created and destroyed per round.** `run_live_improve_round`
(`live_construct.py:1216-1225`) calls `drive_improve_round` without the
`authority` keyword. Inside, `granted is None` reaches
`_disposable_authority("invl02-improve")` at `improve_channel.py:2192-2198`,
which runs `CREATE DATABASE` (`s09_run_isolation.py:260`) and
`DROP DATABASE ... WITH (FORCE)` (`:277`). `_run_source` then settles its
receipt against that disposable dsn.

So the live path holds a real, named `investigations` row and still executes
against a database destroyed when the round ends. Production receipts do not
survive the round.

This is why M1 cannot be a pure column migration. Moving state into SQL while
execution authority is disposable would produce a mission whose records point
at a database that no longer exists — precisely the "summaries into SQL columns
nobody consumes" failure, one level down.

It is also why `_disposable_authority` must stay. `test_inv_a8_improve_authority.py:231-247`
asserts it is present in `drive_improve_round`, and the test's own name and
docstring state the invariant: this is the one place allowed to own a ledger, so
that a round's operations sit under a single study root. The repair is to make
the *production caller* supply real authority, not to delete the default.

## Two further defects the review surfaced

**`run_e3`'s eligibility screen self-attests.** `run_e3` (`invl02_live.py:2936`)
reads `freeze.json` and `e12-run.json` from disk, then gates on
`frontier-<arm>.json` (`:2998-3015`): `_file_digest(store_path)` must equal
`summary["store_digest"]`, and the summary must equal `e12_arm["frontier"]`.
Every input is a JSON file the same run wrote. There is no `investigations` row,
no `in_flight`, no SQL in the screen at all. Its one SQL call (`:3111`) only
confirms a receipt settled. The map's Lane A contract said the "digest comes
from SQL"; the true statement is that the entire screen must move.

**`permitted_experience` has the wrong default type.**
`migrations/0019_mission_entry.sql:25` declares `DEFAULT '[]'`, a JSON list,
while `mission._JSON_TYPES` requires `dict` (`mission.py:51`). `read_mission`
launders it with `dict(row[...] or {})` at `mission.py:324`, so a row admitted
without naming the column reads back as `{}`. A study reading the column
directly gets a list where the module promises a dict.

**`frontier.durable` is strictly deletable.** `StoreIdentity.durable`
(`frontier.py:99-102`) returns `self.dsn is not None`. It has **no writer and no
reader**: `frontier.py:884,905,911,914` all read `self.identity` directly. The
real check is `_check_identity` (`:892-916`), which works field by field. This
is not a gap awaiting a writer; the property is dead on both ends.

## Migration cutover points

Seven functions stop reading mission state from JSON. Everything else is
downstream.

1. `invl02_live._run_frontier_investigation` `invl02_live.py:1934`
2. `live_construct.ensure_live_store` `live_construct.py:1081`
3. `improve_channel.drive_improve_round` `improve_channel.py:2139`
4. `improve_channel.execute_operate_action` `improve_channel.py:2023`
5. `live_construct.adopt_live_revision` `live_construct.py:1447`
6. `live_construct.bind_retained_acquisition` `live_construct.py:1409`
7. `invl02_live._write_e12_revision_receipts` `invl02_live.py:2567`

## Verification constraints on M1

- **No green CI baseline exists.** Run `37172638343` is the only run on this
  branch: 3 jobs failed, 4 of 7 suite matrix entries were cancelled at ~100min,
  1 succeeded. 245 distinct FAILED/ERROR test IDs. A lane's regression cannot be
  distinguished from pre-existing red without a committed starting-failure set.
- **`run-e0`/`run-e12` are never invoked by CI.** Verified: no match in
  `ci.yml`. These are manual-operator paths, so CI cannot qualify M1's central
  migration. Acceptance must name the gates explicitly.
- **Nineteen tests read source text**, not behaviour. They were found by
  adversarial review, not by this map's first pass. Any lane renaming a symbol or
  moving a call breaks one of them. `test_a42_chain_demonstration.py:890` is the
  clearest case: it asserts `"FrontierStore("` appears on a line starting
  `store = _frontier.FrontierStore(`, so deleting the JSON store breaks a test
  while breaking nothing real.
- **`tests/check_execution_authority.py` reports green over 48 calls in 4
  files**, covering none of the tests that fail on authority. It is this
  project's named recurring defect recurring inside its own gate.
- **`improve_channel.py:2330` writes `store._doc["round_results"]` directly**,
  reaching past the class's own validation. Those entries escape
  `_validate_round_results` until the next open. A migration that keeps the JSON
  path "temporarily" will launder this rather than fix it.
- **Unknown exposure has no erasure path.** Verified across `advance_dispatch`,
  `reset_dispatch`, `release_reservation`, `admit_receipt`: every erasure needs a
  proof at a fenced generation, and terminal-unknown is write-once. Preserve
  this; do not add a reconciler that treats unknown as zero.