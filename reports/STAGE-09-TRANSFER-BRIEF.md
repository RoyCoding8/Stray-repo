# Stage 9 — transfer brief for the main agent

Written 2026-09-29 on a **different machine** from the one running the main
session. Everything below is verifiable from the repo; nothing here needs the
originating session.

**Fetch:** `git fetch origin && git checkout codex/implementation-investigation-learning-02`
**Tip at time of writing:** `f461f63`. **Read first:** `reports/STAGE-09-HANDOVER.md`.

---

## 1. Status in one table

| | state | where |
|---|---|---|
| **Engineering pass** | **complete** — 52 census rows, 49 closed, 3 left red by decision | `reviews/STAGE-09-SUITE-AFTER.md` §6 |
| **E1** three representations | **complete** — 312 rows, result is a **loss** | `7e1bcff` |
| **E2** experience | **closed unrun, by decision** — instrument qualified | `81f48f7` |
| **E3** selection | **complete** — claim re-read, narrower than previously reported | `91d8c1c`, `72ac1e7` |
| **E4** learner revision | **closed unrun, by decision** — apparatus qualified | `fcf0ce6` |
| **Handover** | **complete** | `b97d8c8`, `f461f63` |
| **TASKS.md** | 36 of 52 rows done; the 16 others are decided, moot, human-owed, or the audit section | `TASKS.md` |
| **Full-suite rerun** | **attempted, did not complete** — see §5 | `.s09suite/e2-attempt{1,2}-*.log` |

**Zero live dispatches this pass, by decision.** Nothing here is a result from a
model call.

---

## 2. What the main agent must know, because it is easy to get backwards

**E1 is a negative result and is not a defect.** `task_utility: loss`, mean
acquired−control **−0.1528**, all three deltas negative. The model chose `ddmin`
unprompted on all three arms; the control chose `greedy` on all three. The arms
genuinely differ for the first time and the acquired one is worse.

**E3's positive-sounding claim is narrower than it was.** The agenda leads the
control at budgets 20 and 30, and **loses to the best rule in the same family at
both** — at budget 20 it is behind the default, 0.157 against 0.253. The lead is
over a control that 96 of 196 rules beat.

**E2 has no panel that can exist, and that is the finding.** A reducer's oracle
and the campaign's grader are the same function: 540 triples, one distinct
verdict. Difficulty is the wrong axis — too hard and too easy are the same
answer. What varies is the *walk*, and the instrument now exists.

**Jev is closed by operator decision, and the router misreports it.** The router
still lists `typesafe-ai/jev` among its 128 models. **That listing is wrong and
will mislead anyone who checks availability that way.** Consequence: no decision
in this stage got dissent; the stage's decisions are accepted unreviewed in the
calibrated sense.

**Do not re-run the E3 or E1 artifacts as if they were fresh.** The E3 artifacts
under `reports/evidence/inv_r1_e3_selection/` are superseded **in meaning** by
`72ac1e7` and were deliberately not edited — a supersession marker is owed.

---

## 3. The single highest-leverage fix, if you want one

**C15, closed at `589eaea`.** The row previously said *the control is never a
distinct method*. It was one level deeper: **the acquired arm never acquired
anything.**

Every "acquired" arm was byte-identical to `ACQUIRED_ORDER_SOURCE`
(`experiments/doubles.py:74`, sha256 `b0bd83b7ec8…`) while
`origin="model-acquired"` was written **unconditionally**, and
`verify_policy_record` checked only that the origin was a *known string*. A
recording double answers on the same operation, settles the same receipt and
passes the same gates. **Nothing above the receipt distinguished it from a live
provider. The receipt does.**

Fixed across four surfaces with a fifth gate leg (`no_earned_acquired_arm`,
`experiments/ad01/s09_verdict.py:670`, `REQUIRED` and `LEG_FAIL`) that
distinguishes "never labelled acquired" from "labelled acquired with no earned
evidence" — the second is the defect, and naming it an absence would report the
discovery as a null result.

---

## 4. Six briefs that were wrong, and the pattern underneath

Worth carrying because it recurs across projects, not just this one.

| asserted | actually |
|---|---|
| no fixed-allocation control in E3 | existed since the study was written; a grep missed the path |
| a `LIKE` fallback needed reconciling | deleted **three days before** its path went live |
| `assert set() >= {...}` is unfailable | failable — the `set()` was the *runtime* operand |
| E2 needs a panel that varies | no panel can; the reducer is a total fixpoint |
| teach `_pin_kind` about `.startswith` | would point a **truncating** test at a shared database |
| E2 needs the `reason` field rendered | the gate reads a different field entirely |

**The unifying failure shape: a test that cannot fail.** `or True` as an
assertion. A `startswith` guard that *admitted* two live databases. A
`claimed_ops` filter asserting arithmetic on a fabricated list. A competence
check covering one budget while the report claimed all of them.

**A check narrower than the claim made from it is worse than no check** — a
reader who follows the citation finds green and concludes the claim holds.

---

## 5. The one open measurement, and why it is not a defect

The full suite was attempted twice, both timed out, and **neither result is
reported as a pass**:

| | bound | load at start | reached | outcome |
|---|---|---|---|---|
| attempt 1 | 900s | 2.15 | 16% | `timeout` 124 |
| attempt 2 | 1500s | 0.13 | 19% | `timeout` 124 |

**What is signal:** the two dot-stream prefixes are **identical to the
character**. Five deterministic failures, named in the handover §4, in three
files that were **already known-open** and are not regressions from this pass
(two are the pre-existing N-74 signature; one is in `ACCEPTED_FINDINGS`).

**Two measurements were withdrawn rather than reported**, because both were
unsound: a cost-per-test ratio built on a wrong denominator (`pytest --co`
collects 4504 outcomes, not the ~3789 a percentage implied), and a "lane load"
explanation that the idle rerun refuted. **Nobody knows yet why the suite
exceeds 3:54 on this tree.** The row says that rather than guessing.

Collection is cheap and is not the cost: `--co` takes 13.35s.

---

## 6. Housekeeping the next session will hit

**`STALE_AFTER = timedelta(hours=4)`** at `tests/conftest_isolation.py:351`, and
it is **pinned by a test** at `tests/test_s09iso_stale_sweep.py:371`. The sweep
only reclaims past four hours, so parallel lanes stack up faster than that window
clears. **958 databases and 9.6 GB accumulated in one session**; 870 were
reclaimed at `--older-than-hours 1`.

**Not changed**, because it is a safety margin against dropping a live run's
stores and the longest observed single pytest run was 380s — 4 hours is 38× that.
Changing the default also changes a deliberately pinned value. **This is a
person's call, and it is recorded as open in handover §5.4.**

The safety of an aggressive `--older-than-hours` rests on a gate closed at
`b6b5e12`: no non-pytest creator can mint a bare 8-hex token, so the sweep cannot
target a live direct run. **Keep that gate if you tune the interval.**

---

## 7. If you pick this up, do this first

1. **Read `reports/STAGE-09-HANDOVER.md`.** It supersedes
   `.s09suite/handover-prior-revision.md`, which describes a tree 154 commits
   back and is kept only as history.
2. **Reconcile the 5563 units** before any new live call. r4's 2294 and an older
   ad01 3269, both `uncertain`, both `outcome=unknown` from a `lost-response`
   receipt. **A `lost-response` is permanently unknown, not zero.** This is why
   E2 and E4 are closed unrun rather than pending.
3. **Decide `STALE_AFTER`** (§6) or accept re-leaking 9.6 GB per session.
4. **Run the suite to completion** if you want the measurement, or accept the
   per-file route and say so in the ledger.

**Do not** re-derive the census, re-litigate E1's loss, or attempt a new E3
comparison without reading `72ac1e7` first.
