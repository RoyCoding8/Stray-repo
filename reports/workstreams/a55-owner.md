# A55 — the §A ownership migration, measured

Branch `wt/a55-owner`, base `bccf677`. Every figure is a census over that tree.
The commands are named so a reviewer can rerun them.

**The migration is not finished.** One of the four §A items plus one duplicate
predicate were unambiguous and are repaired. The rest are inventoried and left
undecided, with both sides written down.

## What was wrong, and what is now

`improve_channel.fresh_round` is the tree's only continuation entry — a second
process picks up an investigation and drives its next improvement round. It
opened with `FrontierStore(store_path)` and no identity. `_check_identity`
refuses a nameless open of any document that records an owner, and
`live_construct.ensure_live_store` records the owning investigation in every
document it writes. So the entry could continue only stores that no live run
produces.

It now takes `dsn` and `investigation_id` together and opens under that owner.
Both absent still opens namelessly, which keeps the fixture boundary working.
This is a join, not a new requirement on every caller.

A42 had already measured this defect, in
`test_fresh_round_cannot_open_a_store_that_names_a_durable_owner`, and
deliberately declined to fix it: "the repair is a decision about which
investigation owns that store, which is not a measurement's to take." §A
assigns that decision to the ownership migration, so the decision is taken here.
The guard test is unchanged and still refuses both directions.

## The four §A items, each measured

Production-only AST census over the whole tree.

| Item | Held in | Write sites | Read sites | Durable AD01 owner? |
|---|---|---|---|---|
| private state | `_doc["private_state"]` | 3, all `frontier.py` | 1, `frontier.py` | **No.** No other production module reads or writes it. `policy_action.py:121` names it only to forbid a different meaning for the word |
| active source/version lineage | `_doc["active_package"]`, `_doc["lineage"]` | 4, `bind_active` / `adopt_revision` | 4 | **No.** The `active_program` column exists and is written by `twodomain.py:468` with a different value; nothing reconciles the two |
| pending effects | `_doc["pending_effects"]` | 1 append, `_admit_and_spend:1982` | 11 | **Partly, by design.** `mission.py:550-557` states that `mission.is_quiescent` deliberately does not fold these in |
| continuation identity | `_doc["round_journal"]`, `staged_candidate`, `round_results` | 4: 3 in `frontier.py`, 1 in `improve_channel.py` (`round_results`) | 7 | **No.** `in_flight` carries `program_digest`/`input_identity`, but keyed on attempts, not round/step |

## The production entry points

`live_construct.ensure_live_store` is the public entry. Its production caller
set is **one**: `scripts/invl02_live.py:1948`, inside
`_run_frontier_investigation`, which is itself called from four sites
(`:2188` control, `:2197` live, `:2685` per-arm, `:2794` a second control).
Every other construction site is fixture or apparatus — `learner_revision` (4,
no dsn), `channel_controls` (1, no dsn), and `fresh_round` itself.

## Two premises refuted

**The chain never opens a frontier store.** The ledger's surgical-closure line
says the frontier "is not migrated to this SQL owner", which reads as "on the
live path, awaiting a join". Measured, it is not on the proven path at all.

`frontier.py` *is* import-reachable from `cli` (through `method_exec`), so
import reachability is the wrong question. Of the 26 call edges from the chain's
closure into the three modules that name `frontier`, the only one into
`live_construct` is `trajectory:1431` → `find_acquisition_operation`, which
reads SQL and parses response bytes. Both store-opening sites in that closure
(`live_construct:1495`, `:1372`) sit in `live_frontier_round` and
`bind_live_revision`, which no chain edge enters.

**`mission.is_quiescent` still has zero production callers.** A previous lane
measured this and it has not changed. The A42 census independently agrees:
`prod_callers=0`, `reachable_from_main=False`, `test_modules=2`.

## What was deliberately not decided

Two quiescence predicates remain, `mission.is_quiescent` over `in_flight` and
`FrontierStore.is_quiescent` over `pending_effects`. Each has exactly one
production caller. They can disagree, and an investigation can carry an
unresolved frontier effect and no in-flight row.

Merging them means choosing which list owns "admitted and unrun". That is a
study-semantics call, not a measurement, and §A says not to erase uncertainty to
unblock a study. Recorded, not changed.

The larger open question is the same shape. `twodomain.py` writes the
`frontier` and `active_program` columns with real values and nothing reads them
back; `retained_use` has zero production writers. So those columns are a
projection today. Whether they become the owner or stay a projection is the
decision §A asks for and this lane did not take.

## Historical replay formats

524 JSON files under the evidence roots carry `frontier_version`: 512 with no
marker at all, **7 `invl02-frontier-v2`**, **5 `invl02-frontier-v1`**, and 8
study-specific markers such as `invl02-live-preflight-v1`.

Measured. The 5 v1 files load as documents and are refused as live stores, and
flipping only the version marker on a valid v2 document is enough to get the
refusal. So the marker is the sole gate, which is what "preserve historical
replay formats without making them another authority" asks for. No
compatibility shim was added.

## §A counterexamples, on the migrated path

| Counterexample | Covered | Result |
|---|---|---|
| missing authority | yes, both halves | `dsn` alone and `investigation_id` alone both refused: "together; one of them identifies nothing" |
| unrelated route | yes | an owner that does not own the store refused: "is owned by investigation 'a55-cx', not 'a55-somebody-else'" |
| changed bytes | yes | a mutated `imp_source` refused: "improvement bytes do not match their digest" |
| pending resume | yes, out of process | a real subprocess reopened the store under its owner and read back 1 pending effect with its `expected_identity` intact and `quiescent=False` |
| no candidate | no | needs `drive_improve_round` and a disposable PostgreSQL database |
| partial response | no | belongs to the broker/admission side, not to continuation identity |
| timeout | no | `os.killpg` has no Windows equivalent; stays in CI or WSL |

## Runtime

Windows-first. This host has no PostgreSQL, and
`tests/conftest_isolation.py` acquires an advisory lock at `pytest_configure`,
so **no test in this repo collects here** — every run below was made from a
directory outside `tests/`, or by calling the module directly. PostgreSQL-backed
checks are in CI on `stray/a55-owner`.

Local red/green, from `.a55-checks.py` against the same code: **4 of 7 green
before**, **7 of 7 after**. `tests/test_a55_continuation_owner.py` reproduces
the same seven in place: **3 failed, 4 passed** with `improve_channel.py`
reverted, **7 passed** with it applied.