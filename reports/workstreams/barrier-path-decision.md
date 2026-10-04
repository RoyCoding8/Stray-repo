# The fate of `settlement.run:suspend_for_barrier`

Read-only investigation, lane `barrier`, branch `wt/barrier`, base `7c09e19`.
No production code, test, or other report was touched. Every count below was
measured on this worktree; where I did not measure something it says so.

## The decision

**Delete `suspend_for_barrier`, `_attempt_investigation` and
`_hold_on_mission_entry`, and repair the three comments that name them, as one
change.** The strongest reason is not that the function is unreachable. It is
that keeping it costs a load-bearing number and buys nothing in return: it is
the only writer of `investigations.in_flight` outside the module that owns the
column, it is the only producer of the `suspended` status and the only writer
of a non-empty `barrier_ref`, and its two docstrings describe a route to a hold
that no code in the tree takes. Deleting it takes the writer census from four
to three, which is the census the tree asserts and the shape the owning module
already has, and it removes the second `in_flight` writer entirely rather than
adding a guard to it. Keeping it would mean keeping a fourth writer whose
invariant differs from the other three, in a column whose entire justification
is that it has one owner.

I found one live defect while measuring that is worth naming regardless of the
decision, because it would be a defect even if the function were reachable:
`suspend_for_barrier` accepts an `ownership_generation` and performs the
`in_flight` write **before** `store.suspend_attempt` checks it, so a stale
generation gets refused at the lifecycle write with the barrier already recorded
on the mission entry. I did not repair it, because the brief forbids touching
production code, and because deleting the path removes it. It is recorded in
"What I could not determine" with the reasoning.

## The reachability census

### Method

Two independent resolvers, both AST, neither a name grep.

**1. My own walker.** A throwaway script parsed every `.py` under `src/`,
`experiments/`, `scripts/` and `tests/` (`__`-prefixed files skipped), 956
files, **zero parse failures**. For the two target names it recorded every
match on five axes: `ast.FunctionDef` (the definition), `ast.Name` (a bare
call), `ast.Attribute` (a qualified call), `ast.Constant` string (any literal
containing the name, which is how a registry or CLI verb would dispatch),
`getattr`/`getattr_static` with the name as the second argument, and `Import` /
`ImportFrom` binding the name. It attributed each hit to its innermost enclosing
`FunctionDef`/`AsyncFunctionDef`/`ClassDef` by line range, or `<module>`.

**2. The repository's own resolver.** `tests/test_a42_chain_demonstration.py`
already ships a reachability census over the same trees with a `__main__` seed
and a caller-graph resolver. I imported the module and called its `_census()`
directly rather than reimplementing it. It reported `prod_files 468` against its
own pinned `EXPECTED_PROD_FILES = 468`, `test_files 498`, `prod_functions 5810`,
`star_imports 0`, `parse_errors {}` — that is, it walked the tree it claims to
walk. **Both resolvers agree.**

### Worktree exclusion, stated explicitly

Every repository-wide `grep` I ran was piped through `grep -v '^\./\.worktrees'`.
This matters here more than anywhere else, because four other lanes hold copies
of these files at `.worktrees/{accscorer,bindauth,currency,m2design,realauth,scorer}`
and a naive sweep counts `src/settlement/run.py` up to seven times. Two further
guards applied to the resolvers:

- The AST walkers take `ROOT` as an explicit argument and only `rglob` beneath
  `ROOT/{src,experiments,scripts,tests}`. `.worktrees` lives at the repository
  root, not under any of those four, so it is unreachable by construction rather
  than by a filter that might be dropped. My walker additionally skipped any path
  with a dot-prefixed component.
- I re-ran the `in_flight` writer enumeration (below) from a script whose `ROOT`
  was `.worktrees/barrier` itself, and I verified the resulting count was 4, not
  16 or 24.

For the record: a plain repo-wide grep of `suspend_for_barrier` **without** the
filter returns hits from `.worktrees/*/src/settlement/run.py` and the sibling
copies of every report and test. Every figure in this report comes from the
worktree-rooted resolvers above.

### Result

My walker's non-docstring hits, in full:

| kind | file:line | enclosing scope |
|---|---|---|
| `def` | `src/settlement/run.py:538` | `suspend_for_barrier` |
| `def` | `src/settlement/run.py:585` | `_hold_on_mission_entry` |
| `name` | `src/settlement/run.py:563` | `suspend_for_barrier` (the internal call) |
| `attr` | `tests/test_inv_c6_suspend_resume.py:347` | `test_suspend_for_barrier_routes_at_the_mission_entry` |
| `attr` | `tests/test_inv_c6_suspend_resume.py:382` | same |
| `attr` | `tests/test_inv_p1_mission_hold_lock.py:111` | `suspend` (a thread target) |

**No `getattr` hit. No CLI verb. No registry entry.** The only string-literal
hits that are not prose are two `strlit` entries in `tests/test_a42_chain_demonstration.py:522`
and `:524`, which are entries in that file's `CAPABILITIES` tuple — a list of
*things to report on*, not a dispatch table.

The a42 resolver's own verdict:

```
settlement.run:suspend_for_barrier      exists=True prod_callers=0 test_modules=2 reachable_from_main=False
settlement.run:_hold_on_mission_entry   exists=True prod_callers=1 test_modules=0 reachable_from_main=False
```

(`prod_callers=1` on the private is `suspend_for_barrier` itself. That is why
the private is a **test-only entry point**, not production-reachable: its one
caller is the zero-caller public function.)

### What I excluded and why

- **`scripts/checkpoint.py`.** Its module docstring at line 15 says
  "`run.suspend_for_barrier` records per-attempt suspension under a barrier
  ref." I read the file. It never imports `settlement.run`; it imports
  `settlement.store` and `settlement.common` only, and its pause/release pair is
  `store.checkpoint_barrier` / `store.resume_dispatch` (lines 154-163), which
  operate on the `control` row's `dispatch_paused` flag, not on `attempts`. So
  the sentence at line 15 is a **false statement in a production docstring**,
  not a call site. See the docstring section below.
- **Star imports.** `star_imports == 0` per the a42 resolver, so no name can be
  in scope via `from x import *`.
- **The settlement HTTP surface.** `src/settlement/api.py:389` maps the `"pause"`
  verb to `store.suspend_attempt`, bypassing `run` entirely. `run.suspend_for_barrier`
  is not on that path. Its `_COMMANDS` tuple (line 371) has no barrier verb.
- **`broker.py`.** It imports `run` as `runmod` at five sites
  (lines 1341, 1496, 1537, 1563, 1603) and calls 14 distinct `runmod.*`
  attributes across 29 sites. I enumerated all 14; `suspend_for_barrier` is not
  among them.
- **`src/settlement/__init__.py`.** No `suspend` export.

### Conclusion on reachability

**`suspend_for_barrier` is reachable only from tests.** Two test modules call it
(`test_inv_c6_suspend_resume.py`, `test_inv_p1_mission_hold_lock.py`), and one of
those (`test_inv_p1_mission_hold_lock.py`) needs real PostgreSQL, which this host
does not have. So on this host the entire path is unexercised; in CI it is
exercised and nothing else is. The distinction matters and the brief asked for
it: this is **not** a path reachable from nothing. It has a live, passing test
suite that pins its behaviour against a real database, including a two-thread
concurrency regression. It is a *tested* island, not dead code.

## The `in_flight` writer census

`in_flight` is a JSONB column on `investigations`, added by
`migrations/0020_mission_in_flight.sql:26`. It holds `InFlightOperation` entries
(`experiments/ad01/mission.py:99-149`) and is the substrate for
`mission.is_quiescent` (`mission.py:510`), which counts the column's length and
is the predicate now wired into mission adoption.

I re-derived the writer set with the same AST approach
`tests/test_a40_admission_wired.py` uses — matching only
`UPDATE investigations SET in_flight` or `INSERT INTO investigations ... in_flight`
as SQL string constants — and then read each write. **Measured total: 4.**

| # | writer | file:line | connection | lock | what it writes |
|---|---|---|---|---|---|
| 1 | `mission.admit_operation` | `experiments/ad01/mission.py:481` | `mission.connect` | `FOR UPDATE` (`:468`) | appends a fully-typed `InFlightOperation`, `status="held"`, `barrier_ref=""` |
| 2 | `mission.resume_operation` | `experiments/ad01/mission.py:599` | `mission.connect` | `FOR UPDATE` (`:581`) | rewrites the whole list, every entry `status="restored"`, `restored_at` stamped once |
| 3 | `mission.release_operation` | `experiments/ad01/mission.py:639` | `mission.connect` | `FOR UPDATE` (`:627`) | rewrites the list with one attempt's entries filtered out |
| 4 | `run._hold_on_mission_entry` | `src/settlement/run.py:635` | `db.read_connect` | `FOR UPDATE` (`:616`) | rewrites the list with one entry's `status` → `"suspended"` and `barrier_ref` → the barrier ref |

### Is writer 4 the same shape as the other three?

**The concurrency discipline matches. The data shape does not.** Those are two
different questions and the answer differs on the second one.

**Concurrency: correct.** All four read and write in one transaction under
`FOR UPDATE`. Writer 4's docstring (`run.py:599-607`) documents that this was
*not* true before lane P1 fixed it, and `reports/workstreams/p1-search.md:14`
records the lost-update defect with a failing-first regression. That repair
stands and is not in question.

**Data shape: divergent, and I measured the divergence rather than reading it.**
I took a row as `admit_operation` would have written it, added one key
(`steward_note`) that another owner of the column might legitimately attach, and
ran the same row through both write paths:

```
keys only in mission output : []
keys only in run output     : ['steward_note']
same keys, same values      : False
mission as_json drops foreign key: True
run write preserves foreign key  : True
```

The three `mission` writers all parse the raw row through
`InFlightOperation.from_json` (`:473`, `:586`, `:632`) and re-serialize through
`as_json()` (`:483`, `:601`, `:641`). That round-trip **normalises** the column:
it drops any key the type does not declare, and it validates `status` against
`IN_FLIGHT_STATES` (`:96`, `:136`). Writer 4 bypasses the type entirely. It
operates on raw dicts (`run.py:623`, `:630-633`) and replaces two keys with
`dict(raw, status="suspended", barrier_ref=barrier_ref)`. Consequences:

1. **Writer 4 is the only path that can persist a key `mission` cannot read.**
   `from_json` ignores unknown keys on the way *in*, so the row still parses —
   but the next `admit_operation` or `resume_operation` silently strips it.
   The column's shape is therefore determined by whichever writer touched it
   last, which is not a rule anyone wrote down.
2. **Writer 4 is the only producer of `status="suspended"` and of a non-empty
   `barrier_ref`.** `admit_operation` hard-codes `barrier_ref=""` (`:463`);
   `resume_operation` carries `item.barrier_ref` through (`:594`);
   `release_operation` only removes. So `suspended` exists in
   `IN_FLIGHT_STATES` (`:96`) solely for writer 4, and the GIN index at
   `0020_mission_in_flight.sql:32-33`, whose stated purpose is "the operations
   whose restoration a barrier is waiting on", indexes a value nothing produces.
3. **`status` is a field with exactly one reader that branches on it, and I
   could not find any in production.** `mission.is_quiescent` counts the array
   length, not the status (`:539`), and `trajectory.execute_pending` at `:600`
   branches on `admitted is not None`, not on `admitted.status`. I grepped
   `.status` across `src/`, `experiments/` and `scripts/` and found no production
   comparison against an `InFlightOperation.status`. **`NOT MEASURED` at
   runtime**: whether a `"suspended"` row would be picked up by
   `execute_pending` on a resume is a behavioural question I cannot answer
   without PostgreSQL, and I did not guess.

So writer 4 is the fourth writer **with a different invariant**. Per the brief's
framing, that is a latent defect, not mere redundancy. It is a latent defect
today precisely because the path is test-only; wire it up tomorrow and writer 4
becomes the one that can widen the column's shape and the one that produces a
state no reader distinguishes.

### Does the count move?

**Under my recommendation: 4 → 3.** One assertion depends on it and it fails
until repaired in the same change:

- **`tests/test_a40_admission_wired.py:455`** — `assert sorted(found) ==
  sorted(_EXPECTED_WRITERS)` in
  `test_no_production_path_writes_the_column_beside_the_mission_module`.
  `_EXPECTED_WRITERS` is at `:464-469` and lists all four. Removing writer 4
  makes the enumeration return three keys and the assertion fails with
  "the set of functions writing investigations.in_flight changed". This test is
  the count's only enforcement mechanism and it is a good one — it derives from
  the tree rather than from memory. It also has a stale comment at `:460-463`
  ("Measured by the enumeration above at `655d684`") and a stale docstring at
  `:397-398` claiming `mission.admit_operation` "is the only code that writes
  `investigations.in_flight`" — a claim that was already false before this lane
  and is recorded as contradiction #1 in
  `reports/workstreams/m0-ownership-map.md:55-61`.

Also dependent on the count, in prose rather than by assertion:

- **`experiments/ad01/trajectory.py:560-563`** — a docstring stating "four
  writers in two modules" and naming all four.
- **`tests/test_a41_reuse_id.py:25-28`** — prose: "Four production sites write
  `investigations.in_flight` — `admit_operation`, `resume_operation`,
  `release_operation` and `_hold_on_mission_entry`". Note this sentence already
  over-claims: `_hold_on_mission_entry` has no production caller, as this report
  measures. After the deletion the sentence becomes merely wrong; today it is
  wrong in a second way.
- **`tests/test_inv_p2_mission_release_lock.py:3-9`** — prose: "Three of its
  four writers read under `FOR UPDATE`", with line numbers `422`/`507`/`617`
  that no longer match the file (`admit_operation`'s UPDATE is at 481,
  `resume_operation`'s at 599, `_hold_on_mission_entry`'s at 635). This docstring
  describes `_replace`, which pass 2 deleted; it is already stale. Left as-is it
  would go from "stale about a deleted function" to "stale about a deleted
  function plus wrong about the count".

**If the path is kept instead: the count stays at 4** and `test_a40` keeps
passing untouched. That is the one real argument for keeping it, and it is
weak — the count staying put is a *consequence* of the code, not a property
anyone wants. A test that pins a dead writer to be a writer is a test that
forbids the repair.

Two more assertions that would *not* move, and I checked so the reader does not
have to:

- `tests/test_a42_chain_demonstration.py:783`
  (`assert report["prod_files"] == EXPECTED_PROD_FILES`) is a **file** count, not
  a writer count. Deleting three functions from two files does not change it. I
  re-ran `_census()` and confirmed 468 files, 5810 functions. Deleting the
  functions drops `prod_functions` to 5807, but the only assertion on that is
  `> 5000` at `:784`, which 5807 clears comfortably.
- The `CAPABILITIES` tuple at `test_a42_chain_demonstration.py:521-524` lists
  both `suspend_for_barrier` and `_hold_on_mission_entry`. The consuming
  assertions at `:802-836` name `accept_action`, `admit_operation` and
  `is_quiescent` only. The tuple is a reporting surface. `row["exists"]` would
  become `False` and `:854-855`'s `len(live) + len(dead) == len(rows with
  exists)` would hold without them, since it filters on `exists`. **Verified by
  reading; I did not execute the edited tree**, because that would mean editing
  a test.

## What the docstrings claim, and whether they are lying

The brief says two docstrings describe this path. I found **three** in
production code, plus a fourth false claim in a script header.

**1. `src/settlement/run.py:540-561`, `suspend_for_barrier`.** Its central
claim:

> "the operation goes on the mission entry's own in-flight list with its
> program digest and input identity, and that is the record a resume routes at."

The function cannot supply "its program digest and input identity" — it copies
whatever `admit_operation` wrote, which is correct. But the second half is
false as a description of the tree. **No resume routes at that record.**
`trajectory.resume_campaign` restores via `mission.resume_operation`
(`mission.py:562`), which rewrites *every* entry to `status="restored"` and does
not filter on `status="suspended"` or on `barrier_ref` at all
(`:588-597`). The `suspended` state and the `barrier_ref` are written by writer 4
and **read by no production code whatsoever** — I grepped `barrier_ref` across
`src/`, `experiments/`, `scripts/` and `migrations/` and every hit is either
writer 4 writing it, `mission` carrying it through, or the `admit_operation`
docstring at `:449`. There is no reader.

**2. `src/settlement/run.py:587-608`, `_hold_on_mission_entry`.** The claim I
checked hardest:

> "The read and the write are one transaction under `FOR UPDATE`, which is what
> `mission.admit_operation` and `mission.resume_operation` already do to this
> column."

Verified against the source. `run.py:614` opens one connection, `:616-617` takes
`FOR UPDATE`, `:638` commits on that same connection. `mission.py:468` and
`:581` are the same. **This docstring is telling the truth**, and it is the best
prose in the file. It also names `release_operation`'s absence: it says "admit"
and "resume" but not release, because the P1 repair predates the P2 one. Minor.

**3. `migrations/0020_mission_in_flight.sql:28-31`**, the index's stated
purpose:

> "The operations whose restoration a barrier is waiting on. A barrier is a
> reason to hold work; without naming the operation there is nothing for a
> resume to route at, which is how `suspend_for_barrier` came to suspend an
> attempt and record no operation at all."

The first sentence describes a condition no operation is ever in: `resume_operation`
restores everything regardless of barrier state. The second sentence is a
correct historical note about the *old* behaviour. So the index comment states a
present-tense purpose that is not the index's purpose.

**4. `scripts/checkpoint.py:15-16`** — the one I did not expect:

> "Any movement in either interval refuses to certify. `run.suspend_for_barrier`
> records per-attempt suspension under a barrier ref."

**This is false.** `checkpoint.py` never imports `settlement.run`. Its
pause is `store.checkpoint_barrier`, which sets `control.dispatch_paused`; its
release is `store.resume_dispatch`. Nothing in the file suspends an attempt,
and nothing in it writes `in_flight`. This sentence is a production docstring
asserting a call site that does not exist — the same class of defect as the
function under investigation, and it is the clearest evidence that the
documentation and the code have already drifted apart on this exact path.

### Fix the docstring or delete the path?

**Delete the path, and repair the comments in the same change.** A docstring
fix alone leaves a fourth writer to a column whose only justification is single
ownership, with an invariant no other writer holds. A deletion alone leaves four
comments describing machinery that no longer exists. They are one edit, and
splitting them across two changes means an interval in which both are wrong.

Note that the brief's premise — that the two docstrings "assert a behaviour the
code never performs" — is right in substance but slightly off in mechanism. The
code *does* perform what the docstring says, when the function is called. The
lie is that the surrounding system does what the docstring assumes: no resume
routes at the record, and no caller calls the function. That distinction should
survive into the deletion commit message, or a future reader will re-add the
function on the strength of a docstring that still reads as a specification.

## The strongest counter-argument, and why it loses

**The best case for keeping it:** the two docstrings and migration 0020's index
comment are evidence of *intent*. They describe a barrier protocol — a barrier
ref on a held operation, a resume that routes at it — that is specified but not
built. Deleting `suspend_for_barrier` deletes the only executable half of a
design that three separate comments in two languages (SQL and Python) still
describe. If another lane is building the resume side, deleting the suspend side
is destroying a design in flight. And the counter-counter is cheap: the deletion
is one commit on one branch, and the function is 24 lines of body plus two
docstrings.

I searched for that other lane and did not find it. What I checked:

- `reports/PROJECT-LEDGER.md` — one hit for "suspend", at line 659: "**Keep** |
  One mission owner with suspend/resume | C1 retired the partial owners and C6
  gave resume a single owner that names what it resumed." That records
  `suspend_for_barrier` as **already delivered**, not as pending.
- `WORKER-PROMPT.md:53-55` requires that "Admitted work must survive a process
  death with its original source bytes, version, inputs, allocation and
  operation identities" and "Resume must finish or report that work, not
  recompute it under the current program." `mission.resume_operation` and
  `trajectory.resume_campaign` satisfy this. The prompt does not ask for
  barrier-typed suspension, per-attempt or otherwise.
- `docs/design/` — `PRACTICAL-SPECIFICATION.md:201` (REC-1) says "Running work
  must reach a recorded suspension or remain explicitly represented as in
  flight." `checkpoint.py` implements REC-1 via `control.dispatch_paused`, and
  the second clause — "or remain explicitly represented as in flight" — is what
  `in_flight` does. So REC-1 is satisfied without this function.
- `reports/workstreams/inv-c.md:219` identifies the *real* gap, and it is not
  this one: "`resume_campaign` re-arms but does not restore a suspended
  in-flight operation with its old program and input identity". The missing work
  is on the resume side, in `trajectory`, and it wants `in_flight` restored —
  which writer 4's `suspended` status has no part in, because
  `resume_operation` ignores status. `inv-c.md:275` reaches the same conclusion
  as pending work: "route `settled.run.suspend_for_barrier` and
  `context.resume_package`".

**So the counter-argument loses on the evidence, but it wins on sequencing.**
There is no in-flight lane building the other half. The design being destroyed
is a design that three comments describe and no code implements, whose missing
piece is not this function. If a barrier protocol is ever built, the correct
thing to build is a *third* status writer in `mission.py`, next to
`admit_operation`, which holds the column's shape invariant — not a second
writer in a different module with a different one.

Two things strengthen the case for deleting rather than deferring:

1. `reports/workstreams/m0-ownership-map.md:55-61` already recorded this as
   "contradiction #1: a false sole-owner claim", and concluded: "Repair the
   claim or remove the writer, do not add a third." That lane did not own
   `run.py` and left both halves standing. The tree has now carried the
   contradiction for at least one lane.
2. The cost of deletion is *not* zero and I will not pretend otherwise:
   `test_a40_admission_wired.py:455` fails until `_EXPECTED_WRITERS` is edited in
   the same commit, `test_inv_c6_suspend_resume.py` loses two tests,
   `test_inv_p1_mission_hold_lock.py` loses its concurrency regression. That
   last one is a real asset — a two-thread lost-update test against real
   PostgreSQL for this exact column. Deleting the function deletes the test.
   **The regression is worth keeping in spirit**: if a barrier writer is ever
   added to `mission.py`, the race it would have is the same race, and
   `mission`-side coverage of two concurrent barriers would be the right home.
   I did not preserve it, because editing that test is outside my scope.

## What I could not determine

- **Whether a `suspended` row would be executed or skipped on a real resume.**
  `execute_pending` (`trajectory.py:598-600`) branches on `admitted is not None`,
  not on status, which suggests a suspended operation would run — but that is a
  reading, not a measurement. This host has no PostgreSQL, so I could not drive
  it. **NOT MEASURED.** It matters only if the path is wired up.
- **Whether the `ownership_generation` ordering is a live defect or a latent
  one.** `suspend_for_barrier` writes `in_flight` at `run.py:563` before
  `store.suspend_attempt` at `:567`, and `_check_owner` (`store.py:955-958`)
  raises `StaleRevision` inside that second call. A caller passing a stale
  generation therefore gets a refusal *with the barrier already marked
  `suspended` on the mission entry and the attempt still `running`* — the exact
  split state the function's own docstring at `:552-555` says is "preferable to
  the alternative". I could not determine whether any caller ever passes the
  argument: the census found **zero** callers, production or test, that pass
  `ownership_generation`, so no such path exists today. Whether the ordering is
  a defect depends on a future caller, and I am not going to call a defect that
  has no reachable instance. Recorded because deleting the function removes it
  and someone rebuilding the path should not copy the ordering.
- **Whether the `UndefinedColumn` fall-through at `run.py:639-640` is still
  reachable.** It catches `psycopg.errors.UndefinedColumn` and returns, so a
  store on a pre-0020 schema silently records no hold. Migration 0019's absence
  is checkable only against a real database. **NOT MEASURED.** The docstring at
  `:589-593` calls this out honestly, so it is a documented degradation rather
  than a hidden one.
- **Whether the four other lanes' worktrees contain a caller I cannot see.**
  My census is rooted at `.worktrees/barrier` at `7c09e19`. A caller added on
  `wt/accscorer`, `wt/bindauth`, `wt/currency`, `wt/m2design`, `wt/realauth` or
  `wt/scorer` after that commit would not appear here. I did not read those
  branches, because touching another owner's active work is outside my scope.
  **NOT MEASURED.** The ledger and the six worktrees' base commits are the
  thing to check before landing the deletion.
- **What the C6 authors intended by "refuses when there is none."** The refusal
  at `run.py:626-629` is real and tested
  (`test_inv_c6_suspend_resume.py:381-385`), so the intent is not in doubt. What
  I could not determine is why the refusal exists if no production caller exists
  to be refused. Most likely the design anticipated a barrier caller that was
  never built. That is an inference, and I mark it as one.

## Re-running this census

The a42 resolver is already in the tree and needs no scratch file:

```
$ .venv/Scripts/python.exe -c "
import importlib.util
spec = importlib.util.spec_from_file_location('a42','tests/test_a42_chain_demonstration.py')
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
rep = m._census()
for r in rep['rows']:
    if 'suspend' in r['impl']: print(r)
"
```

It reported `prod_files 468`, `parse_errors {}`, and
`suspend_for_barrier` at `prod_callers=0, test_modules=2,
reachable_from_main=False`. Run it from inside the worktree; a run rooted at the
repository parent sweeps the sibling lanes and will report inflated counts.
