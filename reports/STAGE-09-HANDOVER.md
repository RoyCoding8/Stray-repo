# Stage 9 — closeout and handover

Branch `codex/implementation-investigation-learning-02`, at `73dc7fd`. Rewritten
at the close of the expanded pass; the prior revision is preserved verbatim at
`.s09suite/handover-prior-revision.md` and describes a tree 154 commits back.

**This does not claim the assignment is complete.** The engineering pass is
done. The four expanded experiments have their instruments built, qualified and
mutation-verified, and **none of them was run with a live model in this pass.**
What exists is readiness, not results. `TASKS.md` §D still reads 4 COMPLETE and
5 PARTIAL, and that tally is unchanged by anything below.

---

## 1. The handoff, proven rather than asserted

| step | state | evidence |
|---|---|---|
| fetch `codex/stage09-expanded-study-handoff` | done | `refs/remotes/origin/codex/stage09-expanded-study-handoff` = `7ebbb22` |
| cherry-pick `7ebbb22` | done, **rebased** | landed as `dd504e1`; patch-id `cd6f86bd9a796fd198bc8d0c938442dcebe42fdf` on both; `7ebbb22^{tree}` == `dd504e1^{tree}` == `2492b7f4` |
| read the expansion doc | done | `WORKER-STAGE-09-PARALLEL-EXPANSION.md`, 117 lines |
| A–L + R1–R4 scope incorporated | done | this document; `TASKS.md` |

**The cherry-pick is not by hash and a hash test wrongly reports it missing.**
`git merge-base --is-ancestor 7ebbb22 HEAD` returns **false**;
`--is-ancestor dd504e1 HEAD` returns **true**. The change was re-applied under a
new name, so tree equality and patch-id are the real evidence. A patch-id search
scoped to `d8436f0..HEAD` excludes it and finds nothing, because `dd504e1`
predates `d8436f0`.

**Jev is closed by operator decision (2026-09-29), not unavailable by accident.**
**The router still lists `typesafe-ai/jev` among its 128 models. That listing is
wrong and will mislead anyone who checks availability that way.** Consequence:
**no decision in this stage got dissent**, and this stage's decisions are
accepted unreviewed in the calibrated sense. No substitute reviewer was built
and no score was invented.

---

## 2. What this pass actually did

Sixteen lanes, each verified against source before its commit was accepted.
**Nine of them reported a finding that contradicted the brief they were given**,
and in every case the brief was wrong. That is the single most useful thing in
this document and §7 says why.

### 2.1 The engineering pass — 52 census rows, 49 closed

`reviews/STAGE-09-SUITE-AFTER.md` §6 was rewritten at `1f83137` and now records,
per row, what closed it and where. Three rows had false premises and are
corrected rather than silently applied:

- **`assert set() >= {...}` is failable.** The review called it unfailable. The
  source asserts a real set relation; the `set()` in the traceback was the
  *runtime* left operand. Acting on the premise would have cost a lane.
- **`test_m4_clean_baseline` does not need a credential.** The credential is
  present and `preflight_route` succeeds; the code never loads the env file.
- **`test_invc3_export` was 3 rows of one cause, not 4.** The fourth predates
  everything in scope.

**Three rows were left red by decision, each with a named owner:**

| item | why not closed |
|---|---|
| `test_m4_clean_baseline` 2 rows | the obvious fix makes a **test** spend real budget. Now green by a seam instead — `run_output_live` gained the `gateway=` injection `run_output` already had, and the default still builds the real `HttpGatewayAdapter`. **The rows no longer prove the provider honours the frozen route**; they prove the live path's bookkeeping. |
| `test_ag01_experiment` 2 rows | pre-existing N-74 signature, not this stage's |
| one `test_invc3_export` row | the CLI `use` passes no `--policy-source`; what a policy-free use record *should* be is a design question |

### 2.2 C15 — the finding this pass inverted

The row said *the control is never a distinct method*. **It was one level
deeper: the acquired arm never acquired anything.** Every "acquired" arm was
byte-identical to `ACQUIRED_ORDER_SOURCE` (`experiments/doubles.py:74`,
sha256 `b0bd83b7ec8…`) while `origin="model-acquired"` was written
**unconditionally**, and `verify_policy_record` checked only that the origin was
a *known string*. A recording double answers on the same operation, settles the
same receipt and passes the same gates; **nothing above the receipt
distinguished it from a live provider. The receipt does.**

Fixed at `589eaea` across four surfaces, with a fifth gate leg
(`no_earned_acquired_arm`, `experiments/ad01/s09_verdict.py:670`) that is
`REQUIRED` and `LEG_FAIL`. Two real acquisitions followed: `e910a154…` and
`f1b67417…`, both `model-acquired`, both differing from the double.

**E1's result is a loss and stands as one:** `live_acquisition: true` on a real
run for the first time, `task_utility: loss`, mean acquired−control **−0.1528**,
all three deltas negative. The model chose `ddmin` unprompted on all three arms
and the control chose `greedy` on all three. **The arms genuinely differ now,
and the acquired one is worse.**

---

## 3. The four expanded experiments

`WORKER-STAGE-09-PARALLEL-EXPANSION.md` §E1–E4. **Instrument state, not results.**

### E1 — three representations, `7e1bcff`

The `typed-ast` cell and the SWE `World` are wired. 312 rows, 0 refusals, 0
missing cells, 0 repairs. The 30/30 guard result was **re-measured, not
trusted**: `construct/code.inspect` chosen on 30 of 30 independently tallied.

**The typed-ast cell is a projection** over `boolean_ast_policy`'s frozen
loader, and the record says so: `ORIGIN = "fixture-stand-in"`,
`acquisition_evidence.earned: False`. The origin travels in a **sibling key**
because the frozen loader's `_exact` refuses unknown fields. Both directions are
pinned — the gate reads it as a stand-in, and a bundle that *forges*
`model-acquired` is demoted back.

**Two cells could not be filled, and the reasons are representation limits, not
bindings:** the typed AST's frozen `_VIEW_TYPES` publishes no field for the
program under repair; the graph's `_parse_action` deep-copies the action node so
a guard's value never reaches an input, and `code.localize` needs an
already-failed test the load-time `static_view` never has.

### E2 — the panel, `81f48f7`

**I asked for a panel of tasks the authored reducers genuinely fail. It cannot
be built, and that measurement is the deliverable.** A reducer's oracle and the
campaign's grader are the same function: 54 tasks × 2 methods × 5 budgets = 540
triples, **one distinct verdict**. Difficulty is the wrong axis —
`initial-not-preserved` returns the incumbent, and the incumbent of a well-formed
task grades `preserved` *by the well-formedness condition itself*. Too hard and
too easy are the same answer.

**What varies is the walk**, which is what a developing policy reads and is not
the terminal verdict four prior attempts graded. At budget 8 (the freeze's
`MAX_QUERIES`): **108/108 pairs observe both verdicts across 855 graded trials.**

The reading/echoing instrument now exists — the thing four rounds failed to
build:

| policy | on `ad01` | on the new panel |
|---|---|---|
| `COUNT_READS_THE_VERDICTS` | 1.0 | **2.0** |
| `ECHOES_WITHOUT_READING` | 0.0 | **1.0** |
| `PROMPTED_SHAPE_READER` (C15's) | 0.0 | **1.0** |

C15's reader **does not transfer**: it separates on `ad01` only because that
stream was constant. Here it reads, re-plans, and is invisible.

**Not run.** Needs a live model to answer "does a *model* read the stream".

### E3 — the control, `91d8c1c` and `72ac1e7`

**I said no fixed-allocation control existed. One has existed since the study
was written** — `agenda_policy.FixedPolicy`, with both arms in the committed
`e3-crossover.json`. My grep missed `src/settlement/agenda_policy.py`.

The real gap was worse. The competence check exists and passes — **at
`BUDGET = 40`, a module constant, one of only two budgets where the default is
optimal:**

| budget | 8 | 14 | 20 | 30 | 40 | 60 |
|---|---|---|---|---|---|---|
| rules beating `DEFAULT_RULE` | 0 | 0 | **96** | **94** | 0 | 4 |
| rules beating the fitted control | 0 | 0 | 0 | 0 | 8 | **84** |

No constant rule is optimal at all six, and the two arms fail at **different**
budgets. A test asserting optimality everywhere could only pass by naming one
budget and calling it the ladder — the original defect in new clothes.

**The claim is now re-read. E3's sign at 20 and 30 survives; its meaning does
not.** The agenda beats `DEFAULT_RULE` at both and loses to the best rule in its
own family at both (0.419, 0.526); at 20 it is *behind* the default, **0.157
against 0.253**. "The agenda leads on held-out quality at 20 and 30" is an
advantage over a rule most of the space beats, and it is now **asserted**.

**The subtlest finding: those counts are a property of a WORLD SET, not of the
control.** The same 196 rules give 10 beating the default at budget 30 on one
world and 94 on three. The three-world lead is 0.335 against 0.333 and **one
world reverses it.** So the test asserts ">0 rules beat it" and pins the
divergence rather than thresholding a number that would be testing the averaging.

`crossover` is still N-80-broken and was deliberately not built on.

### E4 — the apparatus, `fcf0ce6`

The intervention boundary is `experiments/ad01/improve_channel.py:172`,
`DECISION = "diagnostic-evidence-selection"`. The reviser is scored on the
**descendants**, never on its own task score.

Three controls qualified, plus **a fourth the brief did not ask for and that is
the answer to "which catches a C15-shaped revision."** The existing `disconnect`
control was the wrong shape — a decision the instrument *refuses*. C15 is bytes
that differ and behaviour that does not. `disconnect-bytes` sets the probed
input to `7 if view["experience"] else 3`: admitted **eligible**, both gates
pass, and because experience is empty on the spending step the arm probes the
incumbent's own input 3. **Delta exactly 0.0, se 0.0, over 150 audit seeds, with
a source digest that is not the incumbent's.** Input 7 is the ceiling's argmax,
so the arm sits one unreachable branch from a real gain. The unreachability *is*
the control.

Eleven tests, four controls, all mutation-verified. Recorded as **unpinned**:
the no-op's *fallback* arm is unreachable in a one-step round and mutating it
left all fifteen green.

**Not run.** A live arm is needed to claim benefit and not to qualify the
apparatus. The fourth control does not appear in
`reports/evidence/inv_r1_e4/result.json`, which is superseded history and needs
a **new freeze, not an edit**.

---

## 4. E2, the housekeeping row — attempted, did not complete

**The full suite was attempted twice and timed out both times.** Recorded as
attempted-and-incomplete, not as a pass.

| | bound | load at start | reached | outcome |
|---|---|---|---|---|
| attempt 1 | 900s | 2.15 | 16% | `timeout` 124, SIGTERM |
| attempt 2 | 1500s | 0.13 | 19% | `timeout` 124, SIGTERM |

Logs: `.s09suite/e2-attempt1-loaded.log`, `.s09suite/e2-attempt2-idle.log`.

**What is signal:** the two dot-stream prefixes are **identical to the
character** — 720 of 864 positions, same 5 failures at the same indices, on a
loaded and then an idle box. The 5 are named by mapping the stream onto
`pytest --co` order:

```
tests/test_ag01_demo.py::test_stale_decline_refused
tests/test_ag01_demo.py::test_forged_receipt_observe_refused
tests/test_ag01_experiment.py::test_duplicate_outoforder_wakeup_single_effect
tests/test_ag01_experiment.py::test_duplicate_effect_decisions_charged
tests/test_c14_live_already_spent_source.py::test_the_dead_name_is_no_longer_a_reader_anywhere
```

**All three files were already known-open and are not regressions from this
pass.** The `ag01` pair is the N-74 signature §6 names as pre-existing;
`test_c14_...` is in `ACCEPTED_FINDINGS` in `tests/test_s09_test_db_safety.py`.

**Two measurements I made and then withdrew, because both were unsound:**

- I computed cost-per-test as 0.61× the recorded 3:54 figure, which would have
  said the suite got *faster*. The denominator was wrong — `pytest --co`
  collects **4504** outcomes, not the ~3789 the 19% implied. The rate is not
  reported.
- I attributed attempt 1's slowness to lane load. Attempt 2 at load 0.13 was no
  faster, so that explanation is wrong. **I do not know why the suite takes
  longer than 3:54 on this tree**, and the row records that rather than a guess.

**Collection is cheap and was not the cost:** `--co` takes 13.35s and the
isolation scan runs once, not per file.

**What is left:** one full run with a bound that fits, or the per-file route.
This is a measurement gap, not a defect.

---

## 5. What needs a person

Four items. Each is a decision, not a defect with an obvious fix.

1. **Live spend for E2 and E4 — DECIDED 2026-09-29: do not run.** Both
   instruments are qualified; neither is run, and that is the answer rather than
   a deferral. The blocker was never cost. **5563 units of exposure sit
   unsettled and unreconcilable** — r4's 2294 and an older ad01 3269, both
   `uncertain`, both `outcome=unknown` from a `lost-response` receipt. A
   `lost-response` is permanently unknown, not zero, so a fresh run would add
   unmeasurable exposure to a hole that cannot be closed, and
   `reports/PROJECT-LEDGER.md:110` forbids new live calls before earlier
   exposure is reconciled. Reconciling first is bookkeeping, not dispatch, and
   was not authorised. **Consequence, stated plainly: this stage ends with two
   qualified instruments and no result from either. E2 and E4 are closed
   unrun.**
2. **N-53 / F3 — no dissent.** See §1. Accepting unreviewed decisions is a
   choice; it has already effectively been made by closing the reviewer.
3. **A4b — pre-`a1e1fb3` empty provenance rows.** `receipts.provenance` is
   `NOT NULL DEFAULT ''`, so rows written before the requirement carry the empty
   string and nothing distinguishes them from an admission that named nobody.
   **Backfilling propagates nothing; deleting destroys evidence. Both repairs
   are worse than the recorded limit**, which is why the row is open rather than
   fixed.
4. **`STALE_AFTER = 4h` re-leaks.** 958 databases and 9.6 GB accumulated today
   because the sweep only reclaims past four hours and 16 lanes stack up faster
   than that window clears. The longest single pytest run observed was 380s, so
   the margin is 38×. **870 reclaimed at `--older-than-hours 1`; 88 under an hour
   were kept.** Changing the default also changes a value
   `tests/test_s09iso_stale_sweep.py:371` deliberately pins. **Not changed here** —
   it is a safety margin against dropping a live run's stores, and that is a
   call for a person.

---

## 6. Honest limits of this pass

- **Zero live dispatches, by decision.** No model was called. Every result here
  is a repair, an instrument, or a measurement of a decision already made.
  **E2 and E4 are closed unrun** (§5.1) — not blocked, decided.
- **The suite did not complete.** §4. Five deterministic failures are known and
  named; the rest of the suite is unmeasured at this tip.
- **Nothing here says E1–E4 improve anything.** E1 is a measured loss. E3's
  claim is narrower than reported. E2 and E4 have no result.
- **The `m4` rows no longer prove the provider honours the frozen route.** They
  prove the live path's bookkeeping; the double supplies route metadata.
- **Six of sixteen lanes reported that a brief I wrote was false.** The briefs
  were not the work; the source was. §7.

---

## 7. Process, because the mistakes are the reusable part

**Six briefs I wrote were contradicted by the source, and in every case the lane
was right:**

| I asserted | actually |
|---|---|
| no fixed-allocation control in E3 | one has existed since the study was written |
| the LIKE fallback needs reconciling | deleted 3 days **before** the path went live |
| `assert set() >= {...}` is unfailable | it is failable; the `set()` was runtime |
| E3 needs a new panel that varies | no panel can — the reducer is a fixpoint |
| teach `_pin_kind` about `.startswith` | that would point a **truncating** test at a shared database |
| E2 needs the `reason` field rendered | the gate reads a different field; the verdict is the fixpoint |

**Two of my own mistakes were found by the lanes and neither reached a commit:**
one lane's report arrived with its mutation still live in the shared tree, and
another nearly shipped one. Both self-reported. **Verify every lane claim against
source, and read `git status` after every mutation test** — a background restore
raced a test process's own write in this pass.

**Three lanes edited the main tree instead of their worktrees**, and one staged
a file another lane owned. No cross-contamination reached a commit, but the
convention holds: **one worktree per lane, `git add` named paths, never `-a`.**

**And the pattern the whole project keeps hitting:** a test that cannot fail.
`or True` as an assertion, a `startswith` guard admitting two live databases, a
`claimed_ops` filter asserting arithmetic on a fabricated list, a competence
check covering one budget while the report claimed all of them. **A check
narrower than the claim made from it is worse than no check**, because a reader
who follows the citation finds green and concludes the claim holds.

---

## 8. What the next person should do first

1. **Reconcile the 5563 units before any new live call** (E2 and E4 are closed
   unrun by decision — see §5.1). Until that exists, no dispatch is admissible.
2. **Run the suite to completion** (§4), or accept the per-file route and say
   so. The measurement gap is real and named.
3. **Re-run E3's report against the qualified ladder.** The artifacts under
   `reports/evidence/inv_r1_e3_selection/` are superseded **in meaning** by
   `72ac1e7`; they were not edited, and a supersession marker is owed.
4. **New freeze for E4.** `inv_r1_e4/result.json` has four cells; the fourth
   control needs a fifth.
5. **Decide `STALE_AFTER`** (§5.4) or accept re-leaking 9.6 GB per session.

---

## 9. Where everything is

| | |
|---|---|
| task ledger | `TASKS.md` §A–§G, 52 rows, 36 done |
| census before/after | `reviews/STAGE-09-SUITE-AFTER.md` §6, rewritten at `1f83137` |
| E1 evidence | `experiments/ad01/s09_swe_{binding,ast}.py`, `tests/test_s09_swe_binding.py` |
| E2 panel | `experiments/ad01/panel_variation.py`, `worlds_panel/`, `reports/STAGE-09-E2-PANEL.md` |
| E3 evidence | `experiments/ad01/agenda_policy.py:441`, `tests/test_s09_e3_control_competence.py` |
| E4 apparatus | `experiments/ad01/learner_revision.py`, `tests/test_s09_e4_qualification.py` |
| M4 seam | `scripts/invl02_live.py:1661`, `tests/test_m4_clean_baseline.py` |
| token-grammar gate | `experiments/ad01/s09_run_isolation.py`, `tests/test_sweep_token_grammar.py` |
| prior handover | `.s09suite/handover-prior-revision.md` |
| E2 run logs | `.s09suite/e2-attempt{1,2}-*.log` |
