# Stage 9 M0: the call-chain table needs an owner and a re-read trigger

Lane U4, read-only for the plan. No file under `reports/` was modified. The tip is
`5f5ea22`; the plan was corrected at `7b65027` and that correction is real. This
document does three things: name an owner the repo's convention can carry, say
whether a re-read trigger can be mechanised here, and report how far the six false
rows spread. It does not fix anything in the plan. The exact insertion text is in
section 6 for the coordinator to apply.

## 1. The owner

`WORKER-STAGE-09-PARALLEL-EXPANSION.md:25` states the convention this repo
actually runs on, and it is worth reading literally:

> The coordinator must resolve actual file ownership before dispatch; adjacent lanes
> must not both edit a shared driver. Use a dedicated integration owner for shared
> interfaces.

The table under it (`:27-41`) is two columns, `Lane` and `Deliverable and
evidence`. The plan repeats the same shape in its own ownership table
(`reports/PLAN-STAGE-09-CONNECTED.md:116-133`), which is three columns: `Lane`,
`Owned paths`, `Must not touch`.

**The convention owns paths, not documents.** Every row in both tables is a source
file, a test file, or a review output glob. Not one row in either table claims a
plan or report as its subject. So the honest reading is that the convention cannot
carry "this table has an owner" by itself, and inventing a new column would be
building a mechanism the repo has never used.

The smallest thing that can carry it, using the existing shape exactly, is a row in
the table that is already at `reports/PLAN-STAGE-09-CONNECTED.md:116`. It belongs
to **lane I**, and the reason is not tidiness. Lane I already owns
`experiments/ad01/s09_arm_parity.py`, `experiments/ad01/s09_study_preflight.py` and
`experiments/ad01/s09_study_protocol.py` (`:126`). Every row of the call-chain
table points into those files. `study_ceiling`, `REAL_REPRESENTATION_KINDS`,
`register_typed_ast`, `qualify_pre_launch` and `launch_governance` are all lane I
territory. The table goes stale precisely when lane I edits its owned paths, so the
lane that causes the drift is the only one positioned to notice it. A reviewer
lane would see the drift later and from further away.

There is a second reason to prefer lane I over a fresh R-lane. The four existing
R-lane reviews are one-shot challenges. I grepped all four for `call chain`,
`PLAN-STAGE-09-CONNECTED`, `task graph` and `M0-TASKGRAPH`:

```
R1-AUTHORITY: 0 hits
R2-EXECUTION: 0 hits
R3-VALIDITY: 0 hits
R4-REPRODUCTION: 0 hits
```

That is a grep over the four files, not a read of them, so I label it as such. It
confirms the M0 review's claim at `reviews/STAGE-09-M0-TASKGRAPH.md:235-237` that
no R-lane touches this table. A fifth R-lane would inherit the same one-shot shape
and would have to be re-dispatched by hand to fire again. Lane I is dispatched
whenever its files change, which is the event we care about.

## 2. The trigger

Two events cause a re-read, and they are different events.

**The overtaken event.** Rows 8, 9 and 10 were overtaken because a repair landed on
a line the plan does not name. The detectable fact is ancestry, and I confirmed it
in this checkout at `5f5ea22`:

```
85181b7 ancestor-of 0fa7971: YES
85181b7 ancestor-of f3af21a: NO
85181b7 ancestor-of 14f5733: NO
85181b7 ancestor-of 2b7050a: YES
2b7050a ancestor-of 7b65027: YES
```

`git merge-base --is-ancestor` is the whole check. It is a real, exact, zero-input
command with a boolean exit code, and it does not need the plan to be parsed.

**The wrong event.** Rows 2, 4, 6 and 7 were false about code that already existed.
Ancestry cannot catch this, because the plan was never in the wrong place in git,
only wrong about the source. The detectable fact here is weaker: each corrected
row names a real `file:line`, so a check that asserts those lines still contain the
named symbol would catch a further move. It would not catch a symbol that was never
there. That limit is not fatal because the M0 review is what closed that class, not
a check.

So the trigger is: **re-read rows 1 through 10 when lane I commits a change to any
file named in the Ownership table at `reports/PLAN-STAGE-09-CONNECTED.md:118-129`,
and treat any such commit that is not a descendant of the table's last-verified
commit as requiring a re-read before the table is used for dispatch.**

Note the second clause. It is the one that would have caught this. The table's last
verification is `2b7050a`, which is **not** an ancestor of `f3af21a` or `14f5733`.
Any commit reachable from the branch that is not reachable from `2b7050a` and that
touches a named file is exactly the overtaken condition, and it is a one-line test.

## 3. Is the trigger mechanisable in this repo

**As a CI job or a pre-commit hook: no, and I am not going to propose one.** I
checked the surfaces that would have to exist.

```
.github => absent
.gitlab-ci.yml => absent
.circleci => absent
.pre-commit-config.yaml => absent
Makefile => absent
justfile => absent
noxfile.py => absent
tox.ini => absent
core.hooksPath: (unset)
installed git hooks: (none)
.claude contents: (none)
settings hooks block: (no hooks key)
```

Nothing runs on commit in this repository. A check that nobody runs is a comment
with a shebang, and this repo already has a documented case of a committed
artifact that does not reproduce.

**As a test under `tests/`: yes, mechanically, but I have not run it and the
brief forbids me from running pytest.** `tests/` is the only automated surface this
repo has, and the check would be pure: `git merge-base --is-ancestor` through
`subprocess`, plus a symbol-presence assertion per corrected row. No database, no
child process, no gateway. I am labelling the test *feasible and unexecuted* rather
than *verified*, because I have not seen it pass and this repo's own memory records
that a green gate once hid a skip and a pre-existing stall.

The realistic owner of running it is the same human gate that runs the suite. That
is a real constraint and it is the honest limit of this section: **the trigger is
detectable, and it is not automatically detected.** The check converts "remember to
re-read" into "run one command", which is worth having, and it does not convert it
into "cannot be missed".

## 4. Blast radius of the six false rows

I grepped every markdown file for `PLAN-STAGE-09-CONNECTED`, `M0-TASKGRAPH` and
`CS-01`, then checked whether each citing document repeats a false edge claim
rather than merely citing the file.

### Stale, in the plan itself

**This is the most important finding in the lane, and it is inside the file you
own.** `7b65027` corrected the ten table rows and left the operative instruction
that consumes them. `reports/PLAN-STAGE-09-CONNECTED.md:108-109` still reads, in
the body and not in the review blockquote:

```
108 | The last three rows are the assignment. Each is a missing edge, not a broken one, so the
109 | repair adds the edge and removes whatever stood in for it.
```

Rows 8, 9 and 10 of the table directly below now read `STALE — BUILT`. The
sentence that tells a lane what to do still says they are missing edges to be
built. A reader who takes the table's corrected State column and a reader who takes
the paragraph under it get opposite instructions from the same page. This is the
line that would have sent a lane to re-wire a comparison two commits had already
run, and the correction did not touch it.

**The CS narratives above the table were not corrected either.**
`reports/PLAN-STAGE-09-CONNECTED.md:64-65` still asserts:

> `REAL_REPRESENTATION_KINDS` is `frozenset({PYTHON_STEP})`. The only concrete
> registration helper is `register_python_step`.

I opened `experiments/ad01/s09_arm_parity.py:29` and it reads
`REAL_REPRESENTATION_KINDS = frozenset({PYTHON_STEP, TYPED_AST, ACTION_GRAPH})`.
Row 9's State cell was fixed. The paragraph row 9 is derived from was not.

`reports/PLAN-STAGE-09-CONNECTED.md:44-47` still asserts that
`route_capacity_from_freeze` "multiplies that zero by `max_dispatches` to mint an
`authorized_ceiling_units` of 0". I opened
`experiments/ad01/s09_exposure_ledger.py:503-508` and it now returns a
`DispatchAllowance` built from `limits["max_dispatches"]` with no multiplication
anywhere in that function. The same overtaken class as row 8, in the narrative
instead of the table.

**The M0 inventory state table is frozen and self-labelled.**
`reports/PLAN-STAGE-09-CONNECTED.md:12` says "State read at `dd504e1`" and
`:13` says "Issued against `dd504e1`". Measured now at `5f5ea22`, 239 commits
later:

| Row in the plan | Frozen claim | Measured now |
|---|---|---|
| `:14` Local tip | `dd504e1` | `5f5ea22` |
| `:17` Stale `wt/*` branches | 0 | 0, unchanged |
| `:18` Orphan `worktree-agent-*` branches | 5 | 0, all deleted |

This is not a false row. The file says which commit it was read at, and that label
is doing its job. But a reader who greps the plan for `Local tip` gets `dd504e1`,
and a reader who reads the table as current inventory gets a five-branch claim that
has been untrue since before the correction. The label is the mitigation and it is
already present, so I record this as superseded rather than wrong.

### Stale outside the plan

Every line below I read directly and quote.

| Document | Line | Claim | Status |
|---|---|---|---|
| `reports/STAGE-09-COMPLETION-MATRIX.md` | 28 | the plan is `8712 bytes` | **Stale.** The plan is 11125 bytes. 8712 was its size at `85181b7`, which I confirmed with `git show 85181b7:...\| wc -c`. A byte count is a fingerprint of a past revision and reads as a present-tense one. |
| `reports/STAGE-09-MILESTONE-AUDIT.md` | 21 | "no artifact shows a reviewer challenging the task graph edge by edge" | **Stale.** `reviews/STAGE-09-M0-TASKGRAPH.md` is that artifact, 10 of 10 rows. The same table at `:23` already credits the corrected M2 state, so this document is now internally inconsistent: it accepts the correction for M2 and not for M0. |
| `reports/STAGE-09-CONNECTED-STATUS.md` | 10 | "M0 inventory and map, done, all three findings reproduced at the source" | **Stale on the last clause.** "At the source" is false for CS-01 and CS-03, per the two source reads above. The `done` verdict survives; the evidence for it does not. |
| `reports/STAGE-09-MILESTONE-GAPS.md` | 11 | "No artifact challenges the 10-row call-chain table ... edge by edge" | **Stale.** The row's own remedy column names `reviews/STAGE-09-M0-TASKGRAPH.md`, the artifact that does the challenging. The gap is closed and the row still lists it as open. |

All four are coordinator-owned. I am reporting, not editing.

### Not stale, and worth naming

`reports/STAGE-09-ROADMAP.md:292-293` already carries the corrected M1 and M2
state. Line 293 reads "three registrations in `s09_arm_parity.REAL_REPRESENTATION_KINDS`",
which matches what I read at `s09_arm_parity.py:29`. This is the counter-example: a
document that was written after the repairs rather than before them is not stale.
`reviews/STAGE-09-FINDINGS.md` carries no task-graph claim. I grepped it for
`call chain`, `task graph`, `PLAN-STAGE-09-CONNECTED` and `M0` and got nothing.
Grep only, file not opened, so UNVERIFIED on content.

`TASKS.md:62` reads, from a grep with the line truncated in my output and not
opened in full: "M0 stays PARTIAL and should. Its review found 6 of 10 rows in the
task-graph table false". The review half of that reasoning no longer holds. The
review exists and it is complete. I am not asking for M0 to close, because of
section 5, but the stated reason for keeping it open is now the wrong reason, and a
future reader will keep a milestone open for a reason that has been settled.

## 5. Is M0 closable

**Still open. Not because the table is wrong, and not because no one reviewed it.**

The corrected table at `7b65027` is good. Ten rows, every one carrying a `file:line`
its author opened. The review is complete. If the M0 deliverable were "inventory
plus an independent challenge to the task graph", both halves are discharged and
M0 could close today.

It should not close, because the document that M0 produced still instructs the
opposite of what it now records. Three things are missing, in this order, and all
three are coordinator edits to a file I do not own:

1. `reports/PLAN-STAGE-09-CONNECTED.md:108-109`. The assignment sentence survives
   the correction and contradicts the corrected rows above it.
2. `reports/PLAN-STAGE-09-CONNECTED.md:64-65` and `:44-47`. The CS-01 and CS-03
   narratives are overtaken in the same way rows 8 and 9 were, and were not part of
   the correction.
3. The owner row and the re-read trigger. Section 6 has the text.

The four stale documents in the table above do not block M0. They are downstream
of the plan and become wrong or stay wrong whether or not M0 closes. But if M0
closes with `:108-109` still live, the next dispatch reads the paragraph, not the
State column, and the failure repeats with a fresh lane.

## 6. Exact proposed text for the plan

Three insertions. Line numbers are for the current `7b65027` content and will shift
as you apply them; apply from the bottom up.

### Insertion A, replacing `reports/PLAN-STAGE-09-CONNECTED.md:108-109`

Delete the two lines and substitute:

```markdown
Rows 8, 9 and 10 were the assignment when this table was written at `85181b7`. All
three are now built and the cells above say so. Dispatch nothing from them.

The repair they asked for landed on a parallel line of work and this table was not
re-read against it. The last verification is `2b7050a`, which is not an ancestor
of `f3af21a` or `14f5733`. Any commit that touches an owned path below and is not
a descendant of `2b7050a` needs this table re-read before it is used for dispatch.
```

### Insertion B, a new row in the Ownership table, after `reports/PLAN-STAGE-09-CONNECTED.md:133`

```markdown
| I document | `reports/PLAN-STAGE-09-CONNECTED.md`, this call-chain table | any other plan or report |
```

The prose under the table, appended after the existing lane K / lane L note at
`:138`:

```markdown
Lane I also owns this document. Every row of the call-chain table points into lane
I's owned paths, so the lane that can turn the table stale is the one that owns it.
The R lanes are one-shot challenges and are not a substitute: all four were grepped
for this table and none touches it. When lane I commits a change to any path in the
table above, re-read rows 1 through 10 before the table is used to dispatch.
```

### Insertion C, correcting the two overtaken narratives

Replace `reports/PLAN-STAGE-09-CONNECTED.md:64-69`:

```markdown
**CS-03, representation components, as reproduced at `85181b7`.**
`REAL_REPRESENTATION_KINDS` was `frozenset({PYTHON_STEP})` with one registration
helper. It is now `frozenset({PYTHON_STEP, TYPED_AST, ACTION_GRAPH})` at
`experiments/ad01/s09_arm_parity.py:29`, with `register_typed_ast` at `:571` and
`register_action_graph` at `:645`, built at `0fa7971` and `136e792`. Arms now
branch per kind through the registered `driver_factory` at `:688` rather than
calling `boolean_active.run_episode` for every kind.
```

Replace `reports/PLAN-STAGE-09-CONNECTED.md:44-47`:

```markdown
`route_capacity_from_freeze` then multiplied that zero by `max_dispatches` to mint
an `authorized_ceiling_units` of 0, and the preflight's `Budget` subtracted 5563
carried *reservation units* from that 0 to describe the result as `-5563
dispatches`. Repaired at `f3af21a`: `route_capacity_from_freeze` now returns a
`DispatchAllowance` from `limits["max_dispatches"]` at
`experiments/ad01/s09_exposure_ledger.py:503-508` and multiplies nothing.
```

Both replacements are marked as historical reproduction with their commit named,
rather than silently rewritten, so the next reader can still see what was observed.

## 7. What I did not do

I did not edit `reports/PLAN-STAGE-09-CONNECTED.md`, `TASKS.md`,
`reviews/STAGE-09-FINDINGS.md`, or any milestone matrix. I did not fix a false
row. I ran no tests and treated no test result as evidence. I opened
`reports/PLAN-STAGE-09-CONNECTED.md`, `reviews/STAGE-09-M0-TASKGRAPH.md`,
`WORKER-STAGE-09-PARALLEL-EXPANSION.md`, `experiments/ad01/s09_arm_parity.py`,
`experiments/ad01/s09_exposure_ledger.py`, and
`reviews/STAGE-09-R2-EXECUTION.md:416-420`. The four citing documents in the
section 4 table I read by line extraction rather than end to end. The R-lane
reviews, `reviews/STAGE-09-FINDINGS.md` and `TASKS.md` I grepped only and did not
open. Those three are UNVERIFIED on content and carry no verdict beyond the grep
result quoted.
