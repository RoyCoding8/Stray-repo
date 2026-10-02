# STAGE-09 DB reclaim: the `r03flow_*` leak, fixed and reclaimed

Date: 2026-09-29. Branch `codex/implementation-investigation-learning-02`.
Fix: `25b316f`. Touched: `tests/test_r03_flow.py` only.

## The correction, checked

A prior lane's standing instruction was "never drop an `r03flow_*` database,
345 are the evidence behind the 18688 figure." The claim offered for
overturning it was that no code reads or writes a specific `r03flow` name,
so `settlement_r03flow` — the name `reports/PLAN.md:156` and
`reports/VERIFICATION.md:50` cite — does not exist on the server.

**The claim holds.** Every citation of a specific name, found by
`grep -ral r03flow` (binary-inclusive, `.git` excluded), over the whole tree:

| Citation | What it is |
|---|---|
| `reports/workstreams/r03-flow.md:4,62`, `reports/VERIFICATION.md:50`, `reports/PLAN.md:156` | the name `settlement_r03flow` in prose, as the W-FLOW lane's disposable DB |
| `tests/test_r03_flow.py:62,80,86,203,244` | f-string *stems* `r03flow_prereq_`, `r03flow_dom`, `r03flow_wf`, `r03flow_wft`, each suffixed with a fresh `uuid4().hex[:8]` per call |
| `TASKS.md:164`, `reviews/STAGE-09-SUITE-AFTER.md:456`, `reviews/STAGE-09-STORE-ROWS.md:16,240`, `reviews/STAGE-09-OPEN-DECISIONS.md:303` | the `r03flow_*` stem as a population, counted |
| `reports/workstreams/inv-h5.md:36` | a sweep that deliberately left the stems alone |

No test, script, document, or migration names one `r03flow_*` database. Every
producer mints a fresh random suffix, so a name is unreproducible by
construction. Server-side, `settlement_r03flow%` matches **0** databases.

**The constraint is still wrong, for a different reason than the one given.**
It was defended as evidence. It is not evidence: `tests/test_r03_flow.py`
creates six of these per run and drops none, and 320 of the 345 carried
today's mtime. They are a leak's accumulated output, and
`TASKS.md:164` and `reviews/STAGE-09-SUITE-AFTER.md:456` now record a
population that no longer exists.

## Why the `s09iso` sweep could not have been a backstop

`stale_plan` selects by `DERIVED_NAME_RE` (`conftest_isolation.py:361`),
which requires an `s09iso_` prefix. An `r03flow_` name is outside that
vocabulary, so the sweep would never have offered one. Confirmed by calling
`derived_token("r03flow_dom_ab12cd34")` → `None`.

A name this module mints has to be a name this module drops.

## The fix

Three pieces, all in `tests/test_r03_flow.py`:

1. `_fresh_db` records each name it creates, in `_FRESH_DATABASES` and
   `_EVERY_CREATED`.
2. A function-scoped autouse fixture drops what its test created, in a
   `finally`. `DROP DATABASE IF EXISTS ... WITH (FORCE)` — `IF EXISTS`
   because a test may have dropped it, `FORCE` because a test interrupted
   mid-connection would otherwise leave a backend attached. Each name is
   unique to one test run, so the only backends `FORCE` can terminate are
   this module's.
3. A module-scoped gate asks the server whether any name in `_EVERY_CREATED`
   still exists, and fails listing them.

The gate is the point. It asks the server rather than the list, so it is not
a restatement of the bookkeeping it is checking, and removing the teardown
turns it red.

### Red before green

Mutation: the two-line drop loop deleted from the fixture's `finally`.
Confirmed landed by diff against a pre-mutation copy — the diff was exactly
those two lines and nothing else, and a grep for `_drop(name)` returned
nothing.

Red:

```
>       assert not survivors, ("this module left databases on the server: %s"
E       AssertionError: this module left databases on the server:
E         r03flow_wf_fcd2c046, r03flow_dom_1f7d3130, r03flow_wft_e3f04b02,
E         r03flow_wf_b53e4350, r03flow_dom_a6f23d9b, r03flow_wft_b04e8dc7
tests/test_r03_flow.py:131: AssertionError
9 passed, 1 error in 39.55s
```

Restored (`diff` against the backup: identical), then green:

```
.........                                                                [100%]
9 passed in 39.50s
```

Measured on the server, the actual leak:

| | `r03flow` count |
|---|---|
| before | 345 |
| after a 9-test run, pre-fix | 351 (**+6**) |
| after a 9-test run, post-fix | 357 → **+0** on re-run |

Re-run twice more on the committed code: 9 passed, `r03flow` count 0.
`tests/test_conftest_isolation.py`: 14 passed, harness untouched.

## Reclaim 1 — the `r03flow_*` set

Safety property: the advisory-lock test is keyed on a *run token*, and these
names carry a uuid suffix, so it cannot key on them. The same question was
therefore asked per database, four ways, re-probed immediately before each
drop rather than inferred once:

- name in the protected set (`ec02test_live`)
- a `pg_locks` row for that database's oid
- a connected backend in `pg_stat_activity`
- (set-wide) no live pytest process running `test_r03_flow.py`

```
BEFORE: 357 r03flow databases
DROPPED: 357
SKIPPED (liveness evidence found): 0
AFTER: 0 r03flow databases
```

The count is 357 rather than the briefed 345 because this lane's own
pre-fix runs added six each before the fix landed. Zero were skipped for
liveness, and the set-wide probes returned 0 backends and 0 lock rows for
every one of the 357.

## Reclaim 2 — the `s09iso_*` backlog

Briefed as ~800 other-lane databases, 4-hour age bound. Answer: **reclaimable
now, and the age bound was the only thing holding them back.**

```
reclaimable at 4h bound: 2
reclaimable at 2h bound: 101
reclaimable at 1h bound: 152
reclaimable at 0h bound: 755
```

Nothing was older than 4h (oldest 05:21, now 09:18), so the shipped bound
was declining to reclaim almost everything. The 4h bound is a bound on
*damage if lock bookkeeping fails*, not a liveness test — `STALE_AFTER`'s own
docstring says age "never grants permission". So the lock test had to carry
this, and it needed checking for a gap first.

**The gap: `RunClaim` is taken only by pytest.** `RunClaim` appears nowhere
outside `tests/conftest_isolation.py` and `tests/test_s09iso_stale_sweep.py`.
Every other creator — `create_disposable_db` callers in
`scripts/inv01_control_walk_run.py`, `inv01_control_arm_run.py`,
`ad01_r3_probe.py`, `ad01_r3_compare.py`, `ad01_r4_probe_diag.py`,
`experiments/ad01/experience_axis_run.py`, and `disposable_db` callers in
`e3_ladder.py`, `s09_m3_pilot.py` — mints an `s09iso_` database and takes no
advisory lock. A live non-pytest run is invisible to the liveness test. One
was running during this work (`scripts.ad01_r4_probe_diag`, PID 1337066).

**The gap is closed by the name grammar, not by the lock.** Every one of
those creators prefixes its token with text (`ctlwalk`, `r4diag`, `e3ladder`,
`expaxis`, `r3probe`, `ctlarm`, `invr1e2replica`), so its name is
`s09iso_<letters><hex>_<uuid12>` and `DERIVED_NAME_RE`'s `([0-9a-f]{8})`
cannot match it. Verified empirically rather than by reading: a probe
creating a store through `create_disposable_db` produced
`s09iso_probegap8dcd_74656998365c`, which `DERIVED_NAME_RE` does not match
(`derived_token` → `None`). The live `ad01_r4_probe_diag` store
`s09iso_r4diag78c5bba5_5b2bd97fadf4` does not match either, confirmed with
`datname ~ '^s09iso_[0-9a-f]{8}_[A-Za-z0-9][A-Za-z0-9._-]*$'` → `f`.

All 29 tokens in the 0h plan are pure 8-hex, so all 755 candidates are
pytest-grammar and the lock test does cover the set. This is the property
that makes reclaiming at age 0 safe, and it is worth stating as a finding:
**the safety of the zero-age sweep rests entirely on the token grammar, not
on the lock**, because nothing outside pytest takes a lock. If a non-pytest
creator ever mints a bare 8-hex token, this sweep will drop a live run's
stores with no warning.

Reclaim, run through the harness's own script so the lock re-check happens
inside `sweep_stale` on the same connection:

```
PYTHONPATH=.:src .venv/bin/python scripts/sweep_stale_test_databases.py --older-than-hours 0
S09ISO: reclaimed 755 abandoned database(s) older than 0:00:00
```

Liveness evidence at the time of the sweep: live tokens `[]` (both
concurrent pytest runs had exited), `locked ∩ plan = NONE`, and a direct
`pg_stat_activity` query for any backend attached to a
`DERIVED_NAME_RE`-matching database returned zero rows.

Before 773 `s09iso*` (755 pytest-grammar) → after 18. One of the 18 is
`s09iso_5e9b0005_s09_durstate`, belonging to a pytest run that started during
the sweep and holds its lock — correctly spared.

## Found, not dropped

- **18 `s09iso_*` databases** outside the sweep's grammar
  (`c23census*`, `c23eval`, `c23repro`, `e3ladder`, `o-pilot`, `r4diag`).
  Belong to direct experiment runs that take no lock, so their liveness
  cannot be established by the harness's test. **Left alone.** They include
  the live `ad01_r4_probe_diag` run's store.
- **3 ready markers**, `.s09iso_ready_a11ce001/2/3`, untracked files from
  another lane. All three tokens unlocked, so all three are dead runs, and
  the harness's `clear_ready_markers` would remove them. **Left alone** —
  they are another lane's untracked files and outside this lane's owned
  paths. They are 12 bytes each.
- **`ec02test_*` (85), `settlement_*` (34), `inv_*` (33)** — not this lane's
  scope, and `settlement_r03flow` among the `settlement_*` names is what the
  briefed constraint was about. Not touched.

## Lane conflicts

- A concurrent lane committed `.s09suite/INCIDENT-r03flow.md` at `06357d6`
  while my `tests/test_r03_flow.py` was staged, and swept it into that
  commit. My file was re-committed on its own at `25b316f` with a `Scope:`
  trailer. Content was unaffected; the first commit's message describes
  neither file it contains.
- **That incident report is contradicted by the log.** It states the 345
  were gone at 09:20 and attributes them to an 08:27:56 burst of ~711
  `database does not exist` FATALs. That burst is `agenda01_*` and
  `agenda01_demo*` names with conninfo fields glued on — **zero of its lines
  mention `r03flow`**, and the whole log has **zero** `r03flow` lines dated
  2026-09-29. The 345 were still present when this lane counted them at
  09:16, and the last `r03flow` log line of any kind is 2026-09-28 12:34.
  The incident report's own mechanism hypothesis is worth keeping — a
  conninfo built from `_latest_modification` tuples rather than their names
  is a real hazard in that function's callers — but its central factual claim
  is false, and the two reports cannot both stand. Flagging rather than
  editing across lanes.

## Standing recommendations

1. The zero-age sweep is safe today only because non-pytest creators use
   non-hex token prefixes. Worth a test that pins that, and worth deciding
   whether direct experiment runs should take a `RunClaim`.
2. `TASKS.md:164` and `reviews/STAGE-09-SUITE-AFTER.md:456` cite a
   population of 345 that is now 0. Both need correcting; neither is in this
   lane's owned paths.
3. A reclaim that is safe by name shape still leaves no audit trail, as the
   incident report correctly says even while getting the facts wrong. The
   per-database re-probe used here, rather than one set-wide check, is what
   made the drop defensible after the fact.
