# Stage 9: open decisions for the main agent

Branch `codex/implementation-investigation-learning-02`. First written at
`ec4d719`; this revision re-verified every entry against the source at
`4066470` + `b4e926b`.

Everything under "Needs a decision" is **open on purpose**. None of it was
closed by guessing, by weakening an assertion, or by substituting a number that
could not be sourced. Each entry states what is blocked, what the evidence
actually is, and what a decision would need to contain. The full ledger is
`reviews/STAGE-09-FINDINGS.md`; this file is the decision surface, not the
evidence.

**What changed in this revision, and why it was worth the pass.** Three of the
four open items were wrong, in different ways, and each kind of wrongness
costs a reader time:

- two items were already settled and were still listed as open;
- one counted five blocked seams when the classifier reports **zero**;
- the headline suite figure was from a run that has since been superseded.

**One item needs a person. One needs scope, not a decision. One is new and was
not on any list: a crash in the code N-36 shipped.**

---

## Needs a decision from you

**None open. The last item closed by decision on 2026-09-29; see below.**

### N-53 — closed by decision, 2026-09-29. Jev is no longer available by design.

**This is not an open item and should not be re-probed or re-litigated.**

**DECISION (operator, this session): Jev is no longer supposed to be available.** The
probing below is correct and stays in the record as evidence of *why*, but the 403 is no
longer a gap in this stage's review. It is the intended state.

What the probing established, kept because it is the reason the decision is
comfortable rather than merely convenient:

```
1. jev.py direct (the documented path)
   403  "Free tier users do not have access to this model"   RestrictedModelsError
2. local router 127.0.0.1:4000, model typesafe-ai/jev
   403  "This team is blocked from using AI Gateway."        account_blocked
3. local router, model vercel/typesafe-ai/jev  (the alias)
   500  auth_unavailable -> upstream account_blocked
```

A control model through the same router in the same minute returned 200, so the block
is specific to this gateway account and not to the router or the host. The router still
lists `typesafe-ai/jev` among its 128 models, so **a catalogue check will keep reporting
it as available and that check is wrong.** Anyone who verifies availability by listing
models will reach the opposite conclusion from the one that matters.

**What this stage's decisions were reviewed against instead**, and its honest limit:

| Surface | Gave | Fills the gap? |
|---|---|---|
| Lanes contradicting each other | Real. `13bdb39`, `2f4f046`, `b1d8db2`, `02cdc83`, `7c44088`, `d8e7444` each record a lane being told its own claim was wrong, with the measurement that said so | **Partly.** Genuine challenge, and the reason the seed-recovery and liability figures are sourced rather than asserted. It is not dissent in the calibrated sense: the challenger shares the author's model family, context, and lacks independence. It also leaves no probability |
| 128 routed models at `usage.cost: 0` | Available now, not built into a routine | Would give independence. Would not give typed probabilities |
| This session's own roster: `comment-sicko`, `poteto-agent`, `interrogate`, `principle-attack-the-premise` | Available with no provider access and no dollar cost | Real independence, no calibration. Not a substitute, and not claimed as one |

**The gap that is genuinely not filled:** a decision in this stage has no *calibrated*
second opinion — a number saying "the reviewer holds this at 0.34 likely". A free-form
model asked whether a decision is right produces prose, and prose is what the author of
the decision can also produce. **The independence is real; the calibration is not.** That
is the honest limit, and it is a consequence of the decision above rather than an
unfinished item.

**Consequence for the handover:** this stage's decisions are accepted unreviewed in the
calibrated sense. State it plainly there rather than leaving it to be discovered.

## A defect introduced by N-36, not a decision

`src/settlement/launcher_local.py:692` raises `UnboundLocalError` on the exact
path the N-36 entry claims works. This is a code defect and not a judgement
call, so it is recorded here rather than in the ledger; the file is not in this
lane's owned paths and was left unedited.

**What N-36 promised.** A dispatch that declares `read_deny` on a kernel that
cannot provide the boundary is **refused** rather than run unbounded. That is
the correct behaviour and the claim is true in intent.

**What happens.** The refusal branch calls `self._unwind_claim(paths, seen,
prior_generation)` at line 692, but `seen` is first assigned at line 698,
*after* the branch. On this host — where Landlock is genuinely unavailable, so
the branch is always taken — every such dispatch raises:

```
UnboundLocalError: cannot access local variable 'seen' where it is not
associated with a value
```

**Why it matters, and it is worse than a crash.** The claim at line 656 has
already been made durable to disk by the time line 692 runs, and the unwind
that line 692 was supposed to perform never happens. Measured on this host:

```
1st dispatch  -> UnboundLocalError   (run dir left holding .gen, .pid, .work)
2nd dispatch  -> sent=False, refused_reason='prior-send-recorded'
```

So the operation is **permanently stranded**: a caller that retries — the
correct response to a crash — is told the send already happened, and the
launcher can never dispatch it again. A boundary that refuses a dispatch has
made that dispatch unrunnable rather than refused. The refusal is the feature
N-36 added, and the refusal is the thing that is broken.

**The fix is a one-line move**: hoist the `seen` computation above the
`landlock_available()` check at line 687, or pass a literal `0`. The
`UnboundLocalError` is the visible half; the stranded claim is the half that
would have shipped.

**Why the test suite did not catch it.** `tests/test_n36_containment.py` has
four tests. The two that would exercise this path,
`test_a_declared_read_deny_actually_denies` and
`test_the_deny_does_not_break_a_child_that_needs_only_its_work_tree`, both
`pytest.skip` when `landlock_available()` is false — which is every run on this
host. The refusal branch is therefore executed by **no test on this machine**,
and the two tests that would cover it are skipped precisely where the bug
lives. A green `test_n36_containment.py` here means four tests, two of which
never ran. The third test, the attack itself, passes because it takes the
*un*-denied path, which works.

**One-line fix and one regression test would close it**, and neither needs a
decision. Recorded because it is a live defect on a boundary the previous entry
told the next reader was sound.

---

## Closed, and what closing them cost

Recorded because the method is reusable, not as a status update.

- **N-36 and N-65** — settled by measurement at `94443a7` and `4066470`. Both
  re-verified against the source in this pass, and **both claims hold**. What
  the verification cost and what it found is in
  "Two settlements, re-verified" below.
- **The five seams** — there are **zero**. See below.
- **N-42 / N-75** — a `-q` log's `^FAILED` lines only exist after the run ends,
  so a mid-run grep reads 0. Counting the dot stream is the fix, and the dot
  stream must be *isolated* first: `tr -d '. sxaFE'` deletes those characters
  anywhere in the file, including the test names, and produces a letter
  frequency table instead of a tally. This was got wrong twice in one sitting
  before it was got right.
- **N-72** — a test parsed the test DSN as a URL. The isolation hook produces
  the keyword/value form, which has no scheme, so the parse returned the whole
  string. Both shapes are now handled; verified 10 passed under each.
- **N-75** — one of this branch's own tests asserted that a traversing
  `execution_version` *was* stored verbatim and contained downstream. That is
  the defect N-49 names, so the control could not have caught it. Inverted to
  assert refusal at the boundary plus no operation row written, which is
  strictly stronger; the consumer guarantee is preserved on the values
  production actually passes.

---

## Two settlements, re-verified

N-36 and N-65 were listed as open when they were not. Both were re-derived from
the source rather than taken on the lane's word, and the derivations are short
enough to re-run.

### N-65 — the 18688 figure. **The claim holds, exactly.**

Recomputed through the broker's own schedule, not read off the test:

```
chars=980 -> 2294    chars=1318 -> 2378
chars=981 -> 2294    chars=1319 -> 2378
4 * 2294 + 4 * 2378 = 18688
8 * 2336            = 18688   (2336 is the mean of 2294 and 2378)
```

`broker.exposure_schedule` at `broker.py:149` returns
`(inbound + max_output_tokens) * (retries + 1)` labelled `estimated-budget`, and
that is the only arithmetic path to the number. The two-pricing shape and the
flat-mean shape are both exactly true, which is what kept this open for three
passes: **there was never a per-dispatch price of 2336.** Deducing a
per-dispatch constant from a dispatch *count* is what produced the phantom.

The independent corroboration also holds. `store-reconciliation.json` records
`reservation_amount: 2294` on operation
`invl02-output-872608eb94c3-P1-audit-0023-a1` — an id naming a **P1** request,
which prices at 2294. The store and the schedule agree from two code paths that
never touched.

**Carry 2294 as the evidenced r4 figure, 5563 as the evidenced total, and do not
carry 18688 as liability.** 18688 is a pre-flight sizing of eight requests; r4
spent 1 of 8.

### N-36 — the Landlock boundary. **The mechanism holds; the refusal path is
broken.**

**What holds, verified three ways:**

1. **The probe does not lie, and the thing it catches is real.** This host
   reports Landlock **ABI 8** and `probe_landlock()` correctly returns
   `available=False`. The reason is not a missing kernel feature:

   ```
   C binary, same shell:       rc=0  NoNewPrivs=1
   Python process, same shell: rc=0  NoNewPrivs=0
   ```

   `PR_SET_NO_NEW_PRIVS` returns **success and does nothing** for a Python
   process here — verified through `libc.prctl`, through the raw `syscall(157)`
   entry point, and with explicit `argtypes`. No `LD_PRELOAD`, no seccomp filter
   (`Seccomp: 0`), empty capabilities. Landlock refuses to restrict a process
   that could regain privilege, so a probe trusting the return code would have
   reported confinement that was never applied. Reading the flag back is the
   whole fix, and it is the right call.

2. **The confinement itself works, proven out of band.** A C program in a
   process that *can* set the flag, with `/usr`, `/bin`, `/tmp` allowed:

   ```
   NoNewPrivs: 1
   BLOCKED  /home/ubuntu/AI/Agent-Society-v2/experiments/ad01/worlds.py  Permission denied
   READABLE /usr/lib/python3.12/os.py  64 bytes
   ```

   The denial is real and policies still run. What is unavailable in this
   environment is setting the prerequisite, not the mechanism.

3. **The seed is not in the environment, so the exposure the boundary closes is
   the right one.** The child env is exactly
   `['LANG', 'PATH', 'SETTLEMENT_OPERATION']`, and the last is the operation id.

**What does not hold:** the refusal path, in detail above under "A defect
introduced by N-36". The mechanism is sound; the code that declines to use it
when it is missing crashes.

**Two limits that stand.** gVisor is unmeasured here (`runsc` and `docker` are
absent, so `probe_gvisor` reports it unavailable and `RunscLauncher` refuses),
and `containment=False` on receipts is correct — Landlock confines the
filesystem, it is not gVisor. Raising that label would be the digest the ledger
forbids.

**And the boundary is declared per dispatch, not globally — which means no
production caller sets `read_deny` today.** `read_deny` appears in exactly two
places in the tree: the launcher that honours it, and the test that exercises
it. So the boundary is real, available, and currently unused outside tests. That
is worth saying plainly: N-36 built and verified a door, and nothing in
production walks through it yet.

---

## Needs scope, not a decision

### The five seams: there are none left

`tests/conftest_isolation.py` gave each session its own copy of the shared
`ec02test_*` databases. This entry previously listed **five pinned seams** and
explained what each one cost. That is stale in two ways.

**The classifier now reports 37 of 37 redirectable, 0 pinned.** The docstring
in `conftest_isolation.py:197-205` already recorded why, and the correction is
worth keeping because it is the part that was wrong:

> An earlier version of this docstring claimed the opposite for `in` - that it
> "would hold only because the derived name still carries x". That was false.

`derived_name` builds `s09iso_<token>_<original>`, so the original spelling
*survives* in the derived name and the `in` form does hold — the earlier
explanation, and the entry that repeated it, were both describing a name scheme
this one does not use.

**Of the five listed, three were already rewritten to assert the property** and
are simply missing from the table:

| db | file | why it is fine |
|---|---|---|
| `ec02test_bauth` | `test_bauth_evidence.py` | screens the designation, not the name; truncates |
| `ec02test_m4` | `test_coord02_m4_frozen.py` | `_assert_m4_store` refuses the shared prefix and the `evidence` designation, then returns the name for the fixture to use |
| `ec02test_state` | `test_coord02_state.py` | same designation check |

**The two that were genuinely pinned were stale, and are now rewritten** at
`b4e926b`: `test_ad01_traj.py` and `test_p3e_entry.py`. Both asserted
`DSN.split("dbname=")[1].split()[0] == "ec02test_<name>"`, and both truncate
their store — so the property is real and the spelling was not. They now refuse:

```
ec02test_*   postgres   template*   *_live   live*   (and a DSN with no dbname)
```

and accept `s09iso_<token>_<original>`. That refusal set is a **superset** of
what the old equality caught: the old assertion would have cheerfully passed a
database named `postgres` and one named `live_store`. No isolation assertion
was weakened to make the seam redirectable.

Proof the rewrite can fail, for both files: each of the seven hazards above
raises `AssertionError`, and the per-run name is accepted. The guard is
load-bearing rather than decorative — reducing it to `if False` makes both
`_assert_disposable_store` functions accept `dbname=ec02test_shared`, measured
directly, and both files were restored and re-verified afterwards. Proof the
seam is now redirectable rather than reworded: with `S09ISO_TOKEN=abcd1234`,
`P3E_DSN` resolves to `s09iso_abcd1234_p3e_entry` and `EC02_ADTR_DSN` to
`s09iso_abcd1234_adtr`, and both files pass against those stores — 18 passed and
31 passed — so the fixtures really did run somewhere other than the shared
database. 345 `r03flow_*` databases untouched; `ec02test_live` never contacted.

**One consequence worth recording, because it is the same defect a third
time.** `test_conftest_isolation.py` had a test asserting that `ec02test_adtr`
was *still pinned* — the live suite was its fixture. Removing the pin turned
that test red. It was asserting a name rather than the property behind it, which
is exactly what the two rewritten seams were doing. Repaired at `3bafb7b`: the
property is now checked against a synthetic module that still pins a name, the
way that file already checks the live-database and refusal-input cases, and the
stale assertion became a statement that the rewrite happened. Mutation-checked
by making `_classify` never pin, which turns three tests red.

### The full-suite number is still not attributable, and the number on file is superseded

The entry previously led with **135 failed / 3701 passed / 5 errors over 3857
tests in 3:06:28**. That figure is from the run before N-415's fix and is no
longer the most recent one on this box. `/tmp/full-suite.log` is a completed
run and its own summary line reads:

```
127 failed, 3964 passed, 14 skipped, 2 xfailed, 2 warnings, 2 errors in
14047.33s (3:54:07)
```

`scripts/census_failures.py /tmp/full-suite.log` regenerates **129 rows across
50 files** from it, which is the census's 129 exactly. The `+263 passing` delta
against 135/3701 is N-415's fix un-skipping 101 files that had never run. Both
numbers describe a tip; neither describes this one.

(`/tmp/full-suite-2.log` exists and is **truncated at ~50%** with no summary
line. It is not evidence of anything and should not be read as a second run.)

**How much of the suite can be predicted without running it.** More than the
entry assumed, because the fixes are *shape-absent* — the bug is a code shape,
and a shape can be checked by reading:

| Group | Count | Predictable how | Verdict on this tree |
|---|---|---|---|
| G1 conninfo via `urlparse` | 29 | grep the fixed sites for an unguarded `urlparse(dsn)` | **Fixed.** `experiments/agenda01/runner.py` now routes through `make_conninfo`; 0 unguarded sites. `test_s09o_pilot.py` guards on `parsed.scheme` and returns `ec02test_x` for conninfo and `db` for a URL — both shapes verified |
| G2 conninfo to SQLAlchemy | (in G1's 2) | — | Fixed at `6fb883d` |
| G6 `record_expenditure` without `operation_id` | 5 | read the call sites | **Fixed.** All four call sites in `test_dev01_compare.py` pass `operation_id=`; the rule is live at `trials.py:202` |
| G10 tests that cannot fail | 6 | read each pin | **4 of 6 fixed.** `HAZARD_CEILING` is 1 with an `ACCEPTED_FINDINGS` set and a second test asserting the docstring's own direction; `test_rec_checkpoint.py` and `test_s09_merged_tip_regression.py` no longer carry their literals. `test_s09_swe_experiment.py:208` and `test_state_operations.py:127` still do |
| G4 `inv_r3_export` hardcoded | 10 | environmental, not code | Still points at a name that must exist |
| G5, G7, G8, G9, singletons | 69 | no single shape | Not predictable without running |

So **roughly 40 of 129 rows are predictable from reading the tree**, and each
prediction above is a shape that is now *absent*. That is the useful part: these
are not forecasts, they are absence-of-cause checks, and a full suite would
confirm rather than establish them.

**The smallest run that would establish attribution.** Do not run the suite.
Run the **50 census files and nothing else**, which is the exact set the
failures were observed in and therefore the exact set the attribution needs.

**Cost, measured rather than guessed.**

- `--collect-only` over the whole suite: **47 s** wall, **4216 tests**,
  collection itself 2.8 s. Collection is not the cost.
- The 50 census files hold **570 tests, 13.5% of the suite**. Largest are
  `test_s09_store_cleanup.py` (63), `test_s09_swe_experiment.py` (57),
  `test_s09_merged_tip_regression.py` (33), `test_ec02ad_verif.py` (28).
- **A 7-file sample of the set took 3m17s** (197.57s wall, 11 failed / 125
  passed / 1 skipped) on 2 cores. Extrapolating by test count, the 50 files are
  roughly **25-40 minutes**, against 3:54 for the whole suite.
- The one file that breaks that model is `test_s09_swe_experiment.py`: 57
  tests spawning **real subprocess episodes**. An 8-file sample including it did
  not finish inside 270 s, and it has already been killed twice this week (once
  at a 50-minute cap, once at 90 minutes at 19% done).

**Recommendation: run the 49, exclude `test_s09_swe_experiment.py`, and report
it separately** as a known-incomplete file rather than folding a timeout into an
aggregate. All 129 census rows are in the 50, and only 1 of the 129 is in the
excluded file, so this costs one row of coverage. That file is already recorded
as having no full-suite figure, so excluding it introduces no new gap.

**What the 7-file sample already showed, and it is not all noise.** Of the 11
failures, one was **caused by the seam fix in this same pass** and is now
repaired — `test_conftest_isolation.py` asserted that a stale pin still
existed, so removing the pin turned it red. That is recorded rather than hidden
because it is the cost of the fix and the fix is right: the test was asserting a
name rather than the property behind it, which is the same defect the two
rewritten seams had. Repaired at `3bafb7b` onto the synthetic-module idiom the
file already used, and mutation-checked in both directions. The other 10
failures are the census's own G9 and G10 rows still standing.

**The three conditions that still travel with any number**, unchanged and not
droppable: the run predates the current tip; it ran on a shared PostgreSQL whose
quietness during the run was never measured; and it is a different PostgreSQL
from this one now, so a rerun is not a comparison.

