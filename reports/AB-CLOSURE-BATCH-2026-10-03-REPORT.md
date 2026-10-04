# A–C closure batch report, 2026-10-03

Integration branch `codex/ab-closure-2026-10-02`, from `5349dab`. Tip `64e1f63`,
70 commits. Remotes equal. Evidence delta empty against `reports/evidence/` and
`evidence-ad01/` across every commit. Worktrees pruned to zero; three local
branches remain, all `codex/*`; no stray branch on either remote.

This is the handover. It states what was established, what was not, and what the
next owner should distrust.

## What landed

**Milestone A's acceptance chain runs.** `WORKER-PROMPT.md` §A names the chain;
it is now demonstrated end to end on a repaired tree. Three runs, counts read
from rows rather than from the terminal:

| Stage | Evidence |
|---|---|
| permitted experience | 24 investigations, 17 attempts, 34 attempt_observations, 17 policy rows |
| program decision | **17 of 17 `next_action` non-null**; three STEP kinds emitted |
| admitted effect | 80 operations, 80 settled, 80 reservations; 0 campaigns holding work |
| observation | 17 boundary rows, 10 distinct observation ids |
| checked artifact | 12 episodes carry a check, verdict union `{preserved}` |
| retention/binding | **5 capability_releases**: 4 method + 1 policy |
| fresh-process use | 24 records; 8 executed `acquired-sw-3834317f` out of process |

Method release and policy identity are separate as §A requires: the four method
releases share digest suffix `3834317f66d4`, matching the member 8 use records
executed, each record separately carries policy digest `4296a3634b8f`, and only
the policy release carries `policy_version='ad01-policy-step-v1'`.

**Nine false greens closed. Six were the coordinator's own.**

| Defect | Read as | Actually |
|---|---|---|
| CI `heavy` job | archived tests run in CI | `needs: [suite]` reported `skipped` on every red run; the 85 files had never executed |
| `test_inv_z2_red_audit` | gate green, 0 files | `EXECUTORS` named neither guarded executor; matched 0 of 31 sites |
| `s09_pilot.run_study` | exit 0, `episodes=16 use=24` | own `verify.json` said `fail` with 52 problems; `report["complete"]` licensed discarding it |
| `_method_panel` | method release works | `hashlib` read with no import in scope; `NameError` on 6 of 6 runs, blamed on the repair meant to close that stage |
| `test_a43_method_release` | lane complete | 6 of 9 red at the merged tip; merged without running the lane's tests |
| four CLIs | enforcing surfaces | computed a strict verdict, printed it in full, returned 0 |
| `check_execution_authority` | a working guard | asserted CRLF, which is false in CI; reported 2676 bare-LF problems against correct code |
| `heavy` exit code | red when tests fail | guard fired only on an empty failure file, so 146 recorded failures still exited green |
| `test_a49`'s census | catches drift | the coordinator read a stub's argument and called it the stored column |

**Also landed.** 13 bare executor call sites migrated, with the 9 that assert the
authority refusal deliberately untouched — same-shard CI `suite-py3.13-2` went
68 → 55 with 0 new and 13 fixed. Twenty-six files under `tests/_heavy_archived/`
resolved the repository root one level short and now use `parents[2]`: collection
83 → 84 files, 919 → 925 tests, 84 → 99 passing across the changed files, **zero
regressions**. `improve_channel.fresh_round`, the tree's only continuation entry,
could continue only stores no live run produces and now takes `dsn` and
`investigation_id`. The prospective grant and cap sheet are frozen at
`reports/cap-sheets/a57-prospective-freeze.md` with **zero dispatches and zero
model calls**.

## Not done

1. **Live acquisition has never run.** No credential exists on this host.
   Everything measured was doubles through the fixture gateway. `c4-live` and
   `b5-sealed-state` are unrun §C deliverables, and the chain result above says
   nothing about live acquisition.
2. **Three of §A's four ownership items have no durable owner** — private state,
   active source/version lineage, pending effects. `twodomain.py` writes the
   `frontier` and `active_program` columns with values nothing reads back, and
   `retained_use` has zero production writers. Both readings are in
   `reports/workstreams/a55-owner.md`; the decision is study semantics.
3. **Milestone B is unpowered, and code cannot fix it.** 402,233 op programs over
   the software world's own alphabets reach two signatures from an observable
   space of eight, forced by the fault branches at
   `experiments/representation/software.py:100-143`. Four clusters are two units
   wearing four names. Closing the gap means new fault branches — changing what a
   software task is.
4. **The Boolean instrument** carries one hypothesis class, a module-level
   constant at `boolean_rule.py:228-233`, across 72 tasks with 72 distinct truth
   tables. No panel choice moves it.
5. **A contract disagreement, left open.** `checker._verify_refusal` requires all
   four fields read `refused`; the refusal record deliberately names the admitted
   method in `requested`/`selected`. Both are right about different consumers.
6. **116 archived tests still fail**, none from this batch: missing PostgreSQL, a
   Windows-refused `git checkout`, the absent POSIX resource module, and
   `WinError 2` from `test_run_bounded.py` spawning a POSIX `.venv/bin/python`.
7. **`tests/test_p2c_ad01_resweep.py`** hardcodes a database
   `ec02test_p2c_unused` the isolation layer never creates. Red on every tree
   since before this batch.
8. **`tests/_heavy_archived/test_s09iso_stale_sweep.py`** cannot be collected:
   dotted import of `tests.conftest_isolation` while `tests/` has no
   `__init__.py`, where three siblings import it plainly.

**Stages 9 and 10 remain incomplete.** §A's chain is demonstrated; its ownership
migration, §B's power, and §C's live leg are not.

## For the next owner

**Recovered work sits in `reports/workstreams/recovered/`.** Nine pre-batch lanes
held roughly 1,300 uncommitted lines. They are preserved as patches, not applied.
`c2-labels` carries dated 2026-10-02 corrections to the disposition table: row 6
is a **closed-unrun question rather than a negative** and does not govern, and the
learner-improvement row collapsed two different experiments — `c4-live` never ran,
while E4 did run and spent 6 of 6 authorized dispatches with 0 of 6 eligible.

**`ci.yml` sets `concurrency: ci-${{ github.ref }}` with
`cancel-in-progress: true`.** Every push kills its predecessor's run on the same
ref; five runs died that way during this batch, one cancelled by the coordinator's
own push. A lane gets one clean attempt per branch, not per commit.

**`pyproject.toml` sets `norecursedirs` to exclude `tests/_heavy_archived/`**, so
the `suite` job never collects that directory. Only the `heavy` job exercises it.

## How the record should be read

Nine coordinator premises were refuted by measurement during this batch. The
pattern, since it will recur:

- A number read off a transient artifact was promoted to a fact and propagated
  into three briefs. The "14 policy rows with NULL `next_action`" reading came
  from a disposable database that did not survive; no committed artifact has 14
  rows, and the bundles account for 16/12/8.
- A figure — "60% of the ceiling has no protocol" — appears in no committed
  document on any branch. It was repeated for hours before anyone checked.
- A count was taken from a log rather than from distinct failures: 55 occurrences
  of a string in tracebacks, reported as 12 failing lines.
- An ambiguous instruction ("the repo root on `/mnt/d`") was completed into a
  decoy path by every lane that read it, and an empty directory reports *success*
  rather than error.

The lanes were right more often than the coordinator was, and several corrected
the record unprompted — one refuted its own conclusion twice, another withdrew a
false-green finding after checking ancestry, a third caught itself in a
`git stash` that stashed nothing and produced a clean test run against a tree
still carrying the fix. The recovery cost was the coordinator's, not theirs.

One process failure belongs here rather than in a defect list: the coordinator
deleted a running lane's worktree three times, using "merged into HEAD" as the
safety test. That test is about commits, and it is trivially true for a lane whose
work is still uncommitted in its working tree. The lane recovered from reflog each
time and converged on the identical fix, which was luck rather than a system. The
correct test is whether a worktree has uncommitted changes or unpushed commits.