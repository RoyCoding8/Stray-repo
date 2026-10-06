# Assignment report: one persistent mission, then informative learning studies

Date: 2026-10-06. Scope: the WORKER-PROMPT.md M0 to M4 assignment, from the
2026-10-03 closure checkpoint to run `37438947445` at `bb947536`.
reports/PROJECT-LEDGER.md owns current status. This report maps that status
onto the milestones and states what is resolved, how, and what remains.

Every count below is derived from a named CI artifact or a named re-run,
never from memory. Where a claim is a reading rather than a measurement, the
sentence says so.

## Verdict per milestone

| Milestone | Verdict |
|---|---|
| M0 implementation contract | **Complete**, measured by reader census |
| M1 production ownership | **Mostly complete.** Two named gaps remain: row identity and the round-results projection |
| M2 connected behavior | **Mechanism earned offline.** The durable route through a real allocation and a subprocess is unconfirmed on CI |
| M3 operational study | **Closed as a measured zero.** A valid null completes the study, not stages 9 and 10 |
| M4 inherited learning decision | **Mechanism measured.** The benefit comparison is a real negative. The durable receipt and the live acquisition attempt remain |
| CI | **Not green, bounded and measured.** The portable Linux job carries 62 cross-platform defect lines. The failure population is named |

## M0. Establish the implementation contract

**Resolved.** `reports/workstreams/m0-ownership-map.md` maps mission state
from four independent readers. The finding that drove everything after it:
migrations/0019 put six JSONB columns on `investigations`, and **five had no
production reader anywhere in the tree**. `retained_use` had no writer
either. The only production readers of the mission row are
`read_declaration` and `read_improvement_mode`, and the first discards all
six columns.

The map was challenged by a lane commissioned to refute it, and the
challenge refuted the map's lane section rather than its ownership census:
there are **nineteen source-text gates**, not the one the map named,
resolved from real imports rather than guessed aliases
(`reports/workstreams/m0-map-challenge.md`). The lane split was superseded
to five lanes before any lane was dispatched, which cost a document revision
instead of three lanes of rework.

The five write-only columns were dropped **forward** in migrations/0021
(`54112be`), not by rewriting 0019, because `apply_migrations` records each
file by name and a rewrite would have left two schemas both claiming to be
the schema. Four test files that read the dropped columns were migrated
(`2fcc217`); no assertion was deleted, each was pointed at where the content
lives now.

## M1. Finish production ownership

**Resolved.**

**The authority defect.** `run_live_improve_round` called
`drive_improve_round` with no authority, so a live investigation holding a
real `investigations` row executed against a disposable database that was
destroyed when the round ended. Production receipts did not survive the
round. The repair is a **refusal keyed on `store.identity`** (`0bc02d3`),
not a required argument. A required argument would have forced the live path
to write `authority=None`, which is the same silent substitution with a
`TypeError` wrapped around it. The fixture boundary still gets its
disposable store because `create_store()` without an identity leaves it
`None` and the refusal stays inert. Four call sites now carry the leg's
study allocation instead of minting a second one (`ded63a8`, `2a3bff4`,
`5f1354a`).

**The task-view seam.** The frozen AD01 task carries its answer as a
literal key, `fault = "stale-read"`, with the template naming the same fault
by substring on 27 of 27 frozen software tasks. Six call sites handed a
member the raw dict. The split is at the executor, not the call sites,
because `run_member_out_of_process` builds the grading oracle from the same
dict; a call-site filter would have stripped the grader too. Measured at the
seam: the raw task grades `preserved`, the member view grades `invalid`.
`packet.member_task_view` is an allowlist (`7ac77bb`), so a field the world
adds later is denied until someone argues for it. The old
`method_task_view` denylist that let `fault` through was the opposite shape.

**In-flight state.** The writers went from four to three, all in
`mission.py`. The `suspended` state is deleted with its only producers
(`b2d90cf`). `is_quiescent` counts entries and never reads a status, so a
row the module cannot interpret reads as not quiescent. That property is
measured from the predicate, not assumed.

**The run_operate_step seam.** `choose_next_work` reached
`run_operate_step` with no authority, so the arms `observation_dependent`
compares settled on a disposable ledger. Closed: `authority` is a required
keyword on `_control_triple` and forwarded to all three `choose_next_work`
calls, with no second derivation, because a test pins `_study_authority`
called exactly once inside `_run_frontier_investigation` and zero times
inside `_control_triple`. Threading the authority moved three executions per
investigation onto the study allocation, so the ceilings were re-derived by
AST and moved before they could refuse the enabled run: `E0_SANDBOX_CALLS`
19 to 21 and `E12_SANDBOX_CALLS` 30 to 33.

**Two gaps remain, and they are the milestone's unfinished part.**

1. **Row identity.** `invl02_live._live_investigation_id`
   (`scripts/invl02_live.py:1899`) mints `study_root-run_id-label`.
   `trajectory.campaign_id` (`experiments/ad01/trajectory.py:110`) mints
   `ad01-w{world}-{arm}-{seq}-{token}`. Nothing carries one to the other.
   Until a routing field exists, two quiescence predicates remain by
   design, and the test at `tests/test_a34_quiescence.py:241` that defends
   the two-predicate state expires the moment the field lands.
2. **The round-results projection.** `improve_channel.py` still appends to
   `store._doc["round_results"]` directly. The append now asks the store's
   validator and is withdrawn if the store refuses, which closes the
   write-a-document-the-store-would-reopen-refused hole. That is not the
   repair. The repair is a `record_round_result` method on `FrontierStore`,
   or moving the projection to SQL and deleting it.

## M2. Prove the connected behavior

**Mechanism earned offline. Durable route unconfirmed.**

The deliverable question was settled first (task #31): the protocol is
amended, not restated. The measurement that decided it: across 600
two-probe runs over 40 dev seeds on real production source, the arm moves
in 574 and stands still in 26, and the split is exactly the split in the
earned verdict. Every `not_preserved` moves the arm, every `observed` does
not. A protocol that responded to any two observations would have moved all
600, so "responds to evidence" was too weak to be what was measured.

The amendment adds one probe (`SECOND_PROBE_OPPORTUNITY = "z-extra"`, x=11),
because `measured_verdict` returns `unknown` for a rule's first measurement
by construction and the shipped one-probe freeze could not earn a refutation
at all. On the amended freeze, `observation_dependent` reads True on 14 of
15 second inputs, again split exactly by the earned verdict. That
selectivity is what makes the influence causal rather than merely
responsive. The no-op control, which keeps the observation and rewrites only
the verdict, lands where the disconnected arm lands in all 600 runs.

The comparison itself was defective before this batch and the defect is
recorded: the old `observation_dependent` compared the preserved arm against
the refuted arm, and the refuted arm was built by the falsifier writing the
disagreement it was then credited with discovering. It now compares preserved
against disconnected, which is the clause M2 actually states.

Caps were checked rather than assumed. `RESOURCE_KEYS` is
`("queries", "steps")`, so a probe draws on the store's own authority and
never on the study's `sandbox_calls`. `frontier[0]` stays `opp-first` on both
E0 and E12 because every probe costs 2 and sorts before `z-extra`; the
constraint is written down rather than left to the id.

**What is not confirmed.** The end-to-end path through
`run_step_out_of_process`, with a real allocation row and a subprocess, has
not run. Three PostgreSQL-backed tests are written and unexecuted on green
CI, so the durable-receipt claim rests on CI alone. The db shards are stable
at 53 and 34 known failure lines (run `37438947445` against baseline
`37385370187`, zero new, zero fixed), which means those tests have never
been observed passing in the environment that owns them.

## M3. Qualify and run the operational study

**Closed as a measured zero.**

The instruments were repaired before any freeze.

- The scorer's comparison-rewrite identity was unsound: 34 of the 36 shapes
  it fired on were not the identity it documented, and 78 of 425 credited
  candidates were wrong. After `1a47029b`: 230 credited, 0 wrong. A repair
  rate read off the instrument is a lower bound on the repairs a policy
  found, with the other direction held by the mutation census rather than
  assumed.
- The repair verdict became structural rather than sampled (`cb7012c`). A
  gate reading only public module constants now scores 0 of 30 where the
  sampled sweep scored 30 of 30.
- The unit-factor and unit-step guards narrowed to int (task #30), closing
  the `True == 1` hole the docstrings papered over.
- The accumulated regression specs landed (task #28), so a future edit that
  widens a rule fails CI instead of nothing.

The expressive probe answered the question it existed for: 33 of 39 SWE
tasks admit exactly one repair and **zero admit two plausible ones**. Where
a second repair is reachable, it disagrees with the reference on 81 to 1575
of 2106 swept inputs. Those are overfitted coincidences on three scorer
cases, not alternative correct repairs.

The learner's query-selection rule was then frozen (task #35), because
`VersionSpaceLearner` broke ties with `random.Random(seed)` while its
docstring said it did not. The docstring was what the module meant, so the
code changed: the rule is now a total order and the seed has nothing to
decide. The frozen rule identifies all 224 class members within 8 queries,
which is `ceil(log2(224))`, the information-theoretic bound. The freeze also
exposed that the old blind-arm score of 0.5017 was chance, the mean over
random 8-subsets; the fixed `[0..7]` subset scores 0.0600 and the informed
arm reaches 1.0000. And it exposed the real blocker, which was never the
selection rule alone: callers disagreed about which seed to pass, and 22 of
40 dev tasks scored differently depending on which site ran them.

The null was revalidated after the freeze, per leg, by the structural test
of whether that leg constructs a version space at all. Leg (a), the four
AD01 grounds: none does. Leg (b), the SWE cell: it enumerates edits and
scores through `tasks.score`, never building a version space. Leg (c),
Boolean and ordering: the world grammar itself, untouched by any learner
freeze. M3's zero stands for reasons that never touched the instrument that
was frozen.

Two figures from earlier passes were withdrawn as never reproducible
convention-free, and the "28 of 40" collapse figure appears nowhere in any
committed file, so nothing cites it. The corrections are in the ledger.

A valid null closes a study. It does not close stages 9 and 10, and the
matrix keeps them open.

## M4. Test an inherited learning decision

**Mechanism measured. Benefit comparison is a real negative.**

The mechanism is demonstrated offline without a model call
(`reports/workstreams/m4-comparison.md`, harness
`tools/m4_mechanism_harness.py`, artifact
`reports/evidence/invl02-m4-mechanism/mechanism.json`). The effectful control
changes the next descendant-producing episode after restart, and the proof
is a second interpreter rather than an assertion: the store is written, the
process exits, and a fresh `python -c` reopens it and reads x=12 where the
parent's store read x=3. Six frozen-field writes into real revision bytes
are refused by name, and the clean source is admitted, so a refuse-everything
guard would fail the suite rather than pass it.

Gate 6 was closed by execution, not by reading. The revision's STEP source
was executed against the admission view and emits x=12, and the real
predicates evaluated over it give False on all three of
`delegates_to_frozen_reducer`'s tests. The effectful arm is eligible on the
gate that decides eligibility. What needs the database is only the
`_execution_ledger` wrapper that makes the receipt durable.

The benefit comparison is the honest negative. Across all sixteen reachable
inputs on 150 audit seeds, ten arms beat the incumbent, the best is
**+0.006667 at z = +1.49**, and nothing reaches 1.96. The reachable spread
sits inside the cohort's own resampling spread of 0.009778, and the argmax
disagrees with itself across quarters (9, 12, 4, 4). The panel rule returns
`built: false` with the reason recorded. That rule is a rule, not a
hardcoded no, because a test hands `panels()` rows that clear the bar and
requires arms back; a stub that always refuses fails it.

So a live acquisition would buy a panel whose every arm is inside the noise
floor. Acquiring would close the E4 acquisition question and would not
produce a benefit number. The standing free-route authorization does not
change what the arithmetic supports.

**What remains.** `drive_improve_round` under real authority has not run.
Until it does, "the effectful control changes the next descendant-producing
episode" is a fact about the bytes, and the durable receipt behind it is
CI's to confirm. The live acquisition attempt is likewise unspent. Task #5
stays open for both.

## CI: not green, bounded and measured

The assignment says to stop after the frozen opportunities and not spend
days polishing unrelated CI. The polish was bounded, and this is where it
stopped.

**The matrix.** Five jobs plus guards and line endings: two db shards on
ubuntu with PostgreSQL 18, one portable job each on ubuntu, windows and
macos, and the heavy archived job. Python is pinned to 3.13. `uv pip install
--system` replaced pip, measured with failure sets unchanged and install
times down (Windows 30s to 13s, macOS 9s to 2s, ubuntu 14s to 2s).

**What this batch repaired, each measured against a named run.**

- 41 failures closed against the 37335011361 baseline, with 0 new, from the
  token fix, the substitution gate, mission admission, the s89 rerunners and
  six environment repairs.
- The DSN authority split closed (`09a4985b`). Every socket fallback deleted;
  routeless means the authority refuses and the test skips. Run `37438947445`
  against `37418119879`: each port job fixed exactly **655 lines, identical
  across all three platforms, with 0 new ids and 0 route-class residue**.
  The db shards are byte-identical to baseline, which is the evidence that
  routed sessions were not disturbed.
- The authority-guards job prints `OK: every call carries authority` on this
  tree, where at the baseline it claimed that property while 11 tests failed
  on it.
- The CI hang was fixed and measured on the job that used to die: the
  per-token advisory lock deadlock in nested suites, 24 ms from cancel to
  `CREATE DATABASE ... already exists`, closed by not inheriting the
  parent's token.

**Where CI stands.** The portable ubuntu job carries 62 failure lines. That
set fails identically on all three operating systems, which is what
distinguishes a defect from a platform boundary. Its classes are named:
strict-XPASS unit guards (5), model-list preflight drift (6), citation pins
in `test_m0_plan_claims`, untracked supersession evidence markers, the
`KeyError: 'qualified_on'` family, and git-path census tests. The db shards
carry 53 and 34 stable lines of live-acquisition and retention defects that
belong to the next measurement. The heavy job carries 80, including **one
new, unexplained re-break**:
`test_r02_exec.py::test_stop_uses_kill_fallback_and_clears_tracking`, which
the ledger recorded fixed at run `37236035655` and which no commit since
touched. It is recorded as open, not waved off.

**The platform boundary is a number, not a claim** (task #43). Of the
Windows port job's 180 lines, 132 are windows-only and about 90 of those are
the POSIX bounded child: 55 raise the `preexec_fn` refusal directly and the
rest are its downstream shape, where the world answered `stop` or `refused`
because no child could spawn. macOS contributes about 10. The POSIX-only
syscall, runsc sandbox and posix-path classes are 3, 3 and 7 lines. A green
portable job on a POSIX host is the standard the port lane can reach. The
Windows job's honest target is a failure set inside these classes, not
zero.

## Verdicts the finish section requires

WORKER-PROMPT.md separates six claims and refuses to let one imply another.
Each gets its own verdict here.

- **Mechanism.** Measured offline, twice. The effectful control changes the
  next descendant episode across a process restart, proven by a second
  interpreter reading x=12 where the parent read x=3. And the arm's choice
  changes with the earned verdict in 574 of 600 runs, with every
  `not_preserved` moving and every `observed` standing still. Neither is
  asserted from a green test count.
- **Acquisition.** Not attempted live. No credential was present in the
  session, no network call was made, and the route's live status is a 401
  answer at 127.0.0.1:4000. The attempt remains unspent under the standing
  free-route authorization.
- **Utility.** Measured as a valid null. The supported-cell count is zero on
  four grounds (leg (a) and its structural revalidation, the frozen
  version-space rule, the frozen repair verdict). The scorer's own
  certificate was repaired first, so the null does not rest on a broken
  instrument.
- **Transfer.** Not measured. The one-public-entry demonstration across both
  domains is part of the durable M2 route and has not run on CI. Nothing in
  this assignment earns a transfer claim, and the report does not make one.
- **Autonomous selection.** Measured, offline. The choice among programs
  moved only when the earned verdict justified it, and the no-op control,
  which keeps the observation and rewrites only the verdict, landed with the
  disconnected arm in all 600 runs. That is selection driven by evidence, not
  by either observation alone or the clock.
- **Learner improvement.** Measured as a real negative. The best reachable
  arm beats the incumbent by +0.006667 at z = +1.49, under the 1.96 bar, and
  the argmax disagrees with itself across resampling quarters. The panel
  rule returned `built: false` and the reason is recorded in the artifact.
  A negative here closes the question honestly. It does not license
  pretending the panel would have helped.

## What remains, in order

1. **Row identity (M1).** Build the routing field between
   `_live_investigation_id` and `campaign_id`, then unify the two
   quiescence predicates. This is upstream of the full connected
   demonstration.
2. **`record_round_result` on `FrontierStore` (M1).** Delete the direct
   `store._doc["round_results"]` append.
3. **The durable M2 route (M2).** `run_step_out_of_process` with a real
   allocation row and a subprocess, on CI, plus the one-public-entry
   demonstration across both domains.
4. **The durable M4 receipt (M4).** `drive_improve_round` under real
   authority. Then the live acquisition attempt under the standing
   free-route authorization, with the honest expectation that the panel
   it buys sits inside the noise floor.
5. **The 62 cross-platform defect lines**, if the suite is to go green.
   Mostly citation pins, supersession markers, XPASS guards and the
   model-list preflight. Each is small; none blocks a milestone.

Tasks #5 (M4 durable receipt) and #37 (the durable half of the operate seam)
stay open in the task graph. Everything else in this assignment's lane is
closed with a measurement behind it.
