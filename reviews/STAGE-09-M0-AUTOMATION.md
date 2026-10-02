# M0 is PARTIAL, and the trigger is now a check

Lane AA4. Closes the process question `reviews/STAGE-09-M0-OWNERSHIP.md` left
open, and corrects two things that review got wrong. Source tip at the check is
`8c954a6`; the check itself landed at `270c5dc`.

No file under `reports/evidence/` was read for writing, modified or deleted.
Nothing was run against a database, a gateway or a store.

## 1. The answer, and the correction to the review's premise

`STAGE-09-M0-OWNERSHIP.md` section 3 said the trigger could not be mechanised,
and its evidence was an inventory of automation surfaces that read:

```
.github => absent          Makefile => absent
.gitlab-ci.yml => absent    justfile => absent
.circleci => absent        noxfile.py => absent
.pre-commit-config.yaml => absent
core.hooksPath: (unset)
installed git hooks: (none)
```

**That inventory was correct when it was read and is false now.** The review
landed at `6211307`. `githooks/` landed afterwards, at `8e63c55` and `1e16fdb`,
and both are descendants of the review's own tip, so the review could not have
seen them:

```
6211307 ancestor-of 8e63c55 : YES
6211307 ancestor-of 1e16fdb : YES
```

The repo now has a committed `githooks/prepare-commit-msg`, a committed
`githooks/install`, a documented `docs/COMMIT-SCOPE.md`, and a live
`core.hooksPath=githooks`. The review's own sentence, that a check nobody runs
is "a comment with a shebang", is the standard the new check has to meet, and
it does: it is in `tests/`, it runs in the suite that already gates this repo,
and it exits non-zero.

The review labelled the `tests/` route "feasible and unexecuted" because its
lane was forbidden from running pytest. It is now written and executed.

## 2. What is mechanised, and what is not

The review was right that the two failure classes are different. It was wrong
that the second one needs a human.

| Row | Review's verdict | Predicate now | Data |
|---|---|---|---|
| 8, 9, 10 | overtaken, ancestry catches it | `re_read_needed`, a `git log` range over the cited paths | `a1f514c..HEAD` |
| 3 | wrong, cited `exec_profile` | no importer of `exec_profile` under `experiments/` | `OFF_PATH_IMPORTS` |
| 4 | wrong, cited `policy_action.admit` | the symbol is never defined | `ABSENT_SYMBOLS` |
| 6 | wrong, no production importer | AST import scan over `src`, `experiments`, `scripts` | `UNIMPORTED_MODULES` |
| 7 | wrong, no production caller | AST call scan, home module excluded | `UNCALLABLE_SYMBOLS` |
| all 10 | citations rot silently | definition line equals the cited line | `CITATIONS` |

Six predicates, one per review row. `tests/test_m0_plan_claims.py` runs 21
assertions over them, and `test_every_wrong_row_is_matched_by_a_predicate`
asserts the mapping is complete, so a future row added without a predicate is
a visible failure rather than a silent gap.

**What it cannot do.** It proves the table's citations are bound to the source.
It does not prove a cited function is the *right* implementation of the edge
named. `method_exec.run_step_out_of_process` is live, is called by seven
modules, and is at line 1203; nothing here establishes that it is the correct
boundary for row 3. Only a review establishes that, and `M0-TASKGRAPH` is the
one that did. So the wrong class is *partly* mechanised: the mechanical part is
existence, absence, reachability and import. The judgement part is whether the
live function is the edge's implementation, and that stays with a human.

## 3. The plan's own trigger was backwards, and it had already failed

`reports/PLAN-STAGE-09-CONNECTED.md:115-118`, written by the coordinator from
this review's section 2:

> Any commit that touches an owned path below and is not a descendant of
> `2b7050a` needs this table re-read before it is used for dispatch.

The review's own words at `:88-93` said the same thing. Its worked example at
`:67-71` was a table of `85181b7` against four commits, and it did not test
`2b7050a` against `f3af21a` at all, so it never noticed that its own rule
exempts the commit that broke the table:

```
git merge-base --is-ancestor 2b7050a f3af21a    ->  NO
```

The rule is "not a descendant of `2b7050a`". `9a1884d` *is* a descendant of
`2b7050a`, so the rule exempts it. `9a1884d` is the commit that moved
`study_ceiling` from line 1230 to 1250. A trigger that exempts the commit
which falsified the row it was written to protect is a trigger that reports
green on the failure.

Worse, `9a1884d` is an **ancestor** of `a1f514c`, the commit that last wrote
the plan:

```
git merge-base --is-ancestor 9a1884d a1f514c   ->  YES
git show 2b7050a:.../s09_study_preflight.py   ->  1230:def study_ceiling
git show a1f514c:.../s09_study_preflight.py   ->  1250:def study_ceiling
```

So the plan did not drift. It shipped citing a line the source had already
left. `test_the_plan_was_stale_at_the_moment_it_was_committed` pins exactly
that, by reading the plan at `a1f514c` and the source at `a1f514c` and finding
they disagree.

The correct direction is the pin being the commit's ancestor, which is the
range `LAST_VERIFIED..tip`. `re_read_needed` asks that.

## 4. The check is red now, and that is the finding

```
$ .venv/bin/python3 -m experiments.ad01.s09_plan_claims
M0 call-chain table, 20 citations, last verified a1f514c
FAIL 3 commit(s) after a1f514c edited a cited path, so the table needs a re-read:
  a49a9c5 C15: the adapter's probe was the bug, not the checker
  b74f216 C8, C9, C14, C17: an unknown count is a state, and a key that lies
  8c535e3 C15: the child menu no longer answers itself, and the control is measured
ok   all 20 citations hold, 2 absences still hold
```

Three commits after `a1f514c` edited a cited path. Two of them,
`8c535e3` and `a49a9c5`, rewrote `method_exec.py` by 528 lines between them,
and that file is row 3's implementation. `b74f216` changed
`s09_exposure_ledger.py`, which is row 8's.

**Every predicate passes while the table is stale.** All 20 citations resolve
to live symbols, both absences still hold, both dead modules are still dead,
and both unconnected pairs are still unconnected. A reader running the check
would see a table that looks current. The bodies behind two of its rows were
replaced after it was last read. Only the commit range sees that, and only
because the trigger now asks the question in the right direction.

So the honest status is a debt, not a pass. `main()` exits 1, and
`test_the_exit_code_matches_the_report` asserts the exit code agrees with the
report, because the first version printed FAIL and returned 0, which is the
shape of a check that gets read and not obeyed.

## 5. Non-vacuity, shown against the real failures

A check that is green because it is broken is worse than no check. Each
predicate is demonstrated against a defect that actually happened.

| Test | Demonstrates |
|---|---|
| `test_it_would_have_caught_the_absent_symbol` | `policy_action.admit` was cited as an implementation and has never existed |
| `test_exec_profile_is_on_no_path_under_experiments` | row 3's cited executor is real, imported by `src/settlement`, and imported by nothing the study runs |
| `test_the_home_module_exclusion_is_what_catches_row_seven` | `resume_or_step` is defined and re-exported and called by nothing |
| `test_the_unconnected_pairs_still_do_not_import_each_other` | over all 26 commits touching either file, `learner.py` and `policy_assess.py` never import each other |
| `test_the_trigger_is_not_vacuous` | `8c535e3` and `b74f216` really did move cited symbols, and the trigger returns them |
| `test_the_plan_was_stale_at_the_moment_it_was_committed` | the plan and the source disagree at the plan's own last-edit commit |
| `test_pinned_symbols_are_reachable_symbols_not_docstrings` | the scan parses, so a symbol named only in prose is not a definition |

The last one matters because `store.py:1392` names `admit_study_call` in the
docstring of the check that replaced it, which is the trap a text search walks
into and this one does not. `tests/test_s09_store_cleanup.py:410` cites that
line as 1174, which was where it stood when that test was written; the symbol
is the same one and the line has since moved.

## 6. Two things the check got wrong on the way, recorded

**A caller count does not discriminate.** The first version required a
production caller for every cited symbol. Measured against the source, exactly
half the table fails it: 10 of 20 citations have no caller outside their own
module, and they are `construct_live_policy`, `visible_prompt`,
`admit_action`, `_verify_quality`, `resume_or_step`, `_step_remaining`,
`recomputed_accounting`, `study_ceiling`, `route_capacity_from_freeze` and
`launch_governance`. Several of those are the repairs that make rows 8 and 10
true, and `admit_action` is row 4's live admission. The rule would have been
red for the wrong reason on a correct table.

It was removed. What survives is the narrower claim the review actually made:
a symbol that is neither imported nor called is dead, and that is asserted only
for `resume_or_step`, where both hold.

**The review's `resume_or_step` detail is wrong.** `M0-TASKGRAPH:167-172` and
`M0-OWNERSHIP` describe line 285 as the module calling its own function. It is
an `__all__` entry. The symbol is defined at 251, exported at 285, and called
by nothing anywhere including its own module. The conclusion is unchanged and
in fact slightly stronger, but the mechanism is not what either review said.
`test_the_home_module_exclusion_is_what_catches_row_seven` asserts the corrected
version, and asserts the false one stays false.

## 7. M0 status

**PARTIAL.** Not closed, and the plan's table is not the reason.

Closed since the last review: the ten rows are corrected, the paragraph under
them no longer contradicts them, lane I owns the document, the trigger exists
as a command, and the wrong class has a predicate for each of its four rows.

Not closed: the table is three commits behind its own trigger, and the rows
that matter most for dispatch, 3 and 8, sit on files those commits rewrote.
Rows 1 through 10 need a re-read against `8c954a6`, and then `LAST_VERIFIED`
moves forward in `experiments/ad01/s09_plan_claims.py`. That re-read is not
lane AA4's to do silently, because deciding whether a rewritten
`method_exec.run_step_out_of_process` is still row 3's implementation is a
judgement about the edge, and section 2 is why that is a review's job.

**What a human review must still cover**, now stated as a list rather than a
vague residual:

1. For each of the ten rows, is the live implementation the implementation of
   *that edge*, or merely a live function near it. No predicate can decide this.
2. Rows 3 and 8 specifically, against the three commits that rewrote their
   files after the last verification.
3. Whether the "two toys" scope is still the right narrower claim, which is
   M2's line 47 and outside what a citation check can see.
4. Whether joining the trigger into `githooks/` is wanted. It is not done here.
   A prepare-commit-msg hook that ran an ancestry range would fire on commits
   that edit a cited path, but the correct advice depends on which lanes are
   live, and putting a study gate in the commit path would block every lane in
   the repo on a document-drift question. That is a coordinator decision and it
   is not assumed.

## 8. What was not done

Not run: the full suite, per the brief. Not touched: any file under
`reports/evidence/`. Not modified: `reports/PLAN-STAGE-09-CONNECTED.md`,
`TASKS.md`, or either earlier M0 review, all of which are coordinator-owned.
The two corrections this review makes to `M0-OWNERSHIP` are stated here rather
than applied there.

`conftest_isolation.py` ran and reported dropping 36 databases for the run. No
test in the new file names a `dbname`, and none of the 21 assertions opens a
connection; the module reads git, the filesystem and `ast`.
