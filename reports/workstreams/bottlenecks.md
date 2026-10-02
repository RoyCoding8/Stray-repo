# Three architecture-relevant bottlenecks

Lane `BOTTLENECK`. Branch `wt/bottleneck`, from `6d7558c`. Every number below was
recomputed from the evidence directory or read out of source at this tip. The
three governance documents were not touched; this is the analysis that feeds
them.

**What counts here.** A bottleneck is a structural constraint: something in the
design, the boundaries or the measurement apparatus that limits what the
experiments can ever establish, no matter how much engineering follows. A defect
is something that was wrong and can be repaired at the place it is wrong. A
shortfall is a budget or a time. Section 6 separates the three.

**The honest answer is two.** The current ledger names three. One of the three,
the output-budget constraint, was measured and falsified by lane B17 after the
ledger was written, so it is not a bottleneck on this tree. Section 3 says so
with the evidence.

---

## 1. The system has no independent unit for any learning claim

**The constraint.** Every disposition above acquisition rests on comparing two
arms, and the design supplies one independent unit of variation for both
structures, so a contrast on this apparatus has n=1 no matter how many rows it
runs. The system cannot express the comparison it is trying to make, so the
question is not unanswered; it is unaskable.

**Evidence.**

- The cluster rule is `(family, template)`
  (`experiments/ad01/s09_panel_inventory.py:18`), and `minimum_clusters_for_alpha`
  returns `floor(log(alpha)/log(0.5)) + 2` = 6 at alpha 0.05
  (`s09_panel_inventory.py:119-122`).
- Across all 14 frozen panels
  (`reports/evidence/invr1b8-panel-census/census.json`), **exactly three are
  powered** and all three are graph-only: `graph:dev+transfer`,
  `graph:within+transfer`, `graph:dev+within+transfer`, each 6 clusters against 6
  required. **All seven `software` panels are unpowered**, the largest reaching 4
  clusters against 6.
- The Boolean structure offers exactly **1** hypothesis class against 6
  required. Measured here directly from source: every one of the 3 splits x 24
  seeds yields a byte-identical `hypothesis_class` descriptor, `{"form": "affine
  over four inputs, optionally XORed with one pairwise input product", "n_inputs":
  4, "n_outputs": 4, "class_digest": "285113caf4ab", "class_size": 224}`
  (`boolean_rule.py:228-233` gives the descriptor; the census is
  `twodomain.py:98-116`). The 72 tasks carry 72 distinct hidden truth tables
  drawn from one class, so the tasks are distinct and the class is not.
- The SWE side reports **9** and is marked `powered: True`, which is why the
  completion matrix reads the crossing as powered on the SWE side. Recomputed
  from source: **that 9 is 3 dev templates plus 6 held-out ones.**
  `s09_swe_tasks.DEV_TEMPLATES` is `("count-lead-sum", "scan-depth",
  "token-width")` and `HELD_OUT_TEMPLATES` is the other six; `twodomain.py:119-126`
  unions them. On either split alone the SWE side is **3 or 6 against 6
  required**, so the dev side is unpowered and the held-out side is exactly at
  the threshold with zero margin. The union reaching 9 is what turns
  `powered_structures: ["software-fault-repair-v1"]`.

  This is worth naming rather than as a defect, because the union is
  defensible for a *selection* question and indefensible for a *generalization*
  one. dev and held_out exist as separate splits precisely so that a contrast
  cannot read a task it will be scored on. Counting their templates together to
  clear the power threshold re-introduces through the census the leakage the
  split was built to prevent. The crossing then spends 2 dev episodes and 1
  held-out (`twodomain.py:348`), which is the honest ratio and a 3-unit dev
  panel.

**Why architectural.** The fix is not a better generator or a bigger budget. The
Boolean hypothesis class is a published constant
(`boolean_rule.class_digest()`) that every task in all three splits carries by
construction, so the class count is 1 by definition of the instrument and no
panel choice over the existing tasks can move it. Going from 1 unit to 6 needs
six genuinely different *families* of hidden function, which means six different
generators, and "unsupported cells need a concrete witness and an architectural
disposition, not a new DSL built merely to fill the table" (`WORKER-PROMPT.md`
§B) applies to the world, not only to the representation. Inside the current
design this is not a change; it is a different instrument.

**What it blocks.** Task utility and learner improvement, both of which are
comparisons between two arms. Also any two-domain claim: the crossing needs
independent units on both sides and has one on the Boolean side.

**Smallest change that removes it.** Either add five independent Boolean
hypothesis families, or re-scope the claim to what one family can support and
raise `ALPHA` so one unit is honestly sufficient. The second is cheap and
honest. It converts the disposition from "not established" to "not askable at
this alpha", which is a smaller claim and a true one.

---

## 2. The causal chain's own identity is synthesized, so arrows 3 and 4 are bound by position, not by cause

**The constraint.** `s09_policy_state.effect_id` is a string built from the
investigation id and a sequence number. It names no row in any table. The
durable row that would make the effect-to-observation arrow causal does not
exist, so the chain is two durable rows with a positional convention between
them, and "the arrow holds" cannot be established for those arrows by running
more experiments.

**Evidence.**

```python
# experiments/ad01/trajectory.py:257
def _s09_effect_id(cid: str, seq: int) -> str:
    return "ad01-%s-b%d-effect" % (cid, seq)
```

- Written at `:284` and `:307` into `s09_policy_state`, whose column is
  `effect_id TEXT NOT NULL` (`migrations/0017_s09_state.sql:5`).
- `operations.id` is `TEXT PRIMARY KEY` (`migrations/0001_schema.sql:128`) and
  every other identity-bearing table carries a real foreign key to it
  (`receipts.operation_id REFERENCES operations(id)` at `:154`, and again at
  `:165`). **`s09_policy_state` is the one table in the schema with an `effect_id`
  column and no foreign key anywhere.** A repo-wide grep finds no `SELECT`, no
  `JOIN` and no insert producing a row whose `operations.id` equals the
  synthesized value.
- `attempt_observations` is `(id, attempt_id, content, created_at)`
  (`migrations/0001_schema.sql:122-127`). It carries no `operation_id` and no
  `effect_id` column, so the observation side of the arrow cannot be joined
  either.
- `_publish_boundary` (`trajectory.py:1138-1163`) writes `seq`, `task_id`,
  `decision`, `observation_id` and no operation reference.
- The independent reviewer measured it against real PostgreSQL
  (`reports/workstreams/r-final-review.md:118-136`): 3 of 3 synthesized ids
  absent from `operations`, and no observation carrying an operation or effect
  id.

**Why architectural.** This one is *not* a hard fix, and honesty requires saying
so. It is a missing foreign key in a table that otherwise has them, so it is
closer to a defect than bottleneck 1. It earns a place here because of its
*shape*: the chain is the mechanism claim the entire batch rests on, and the
instrument that was supposed to prove it proves a weaker thing than it claims,
and it will keep proving that weaker thing after every other defect in the tree
is fixed. The proof is the existence of the rows; the causal binding is not
tested by anything. The reviewer is explicit that this is a gap beside the
mechanism rather than a regression from it, and that the other five arrows hold.

I rank it second and I would rank it first on severity. The ranking follows
*blocking power on the research claims*, not blast radius.

**What it blocks.** "Mechanism CONFIRMED" cannot be stated for the full chain.
It can be stated for five of seven arrows. Any future claim that a particular
admitted effect produced a particular observation has nothing to read.

**Smallest change that removes it.** Read the real operation id. The broker
already mints one per dispatch and `mission.admit_operation`
(`experiments/ad01/mission.py:385-439`) already records the admitted operation
under `(investigation_id, seq)` with `FOR UPDATE`. So the identity exists at the
admission point and is simply not written into `s09_policy_state.effect_id`.
Write that value through and add the foreign key. **Inside the current
architecture**, and it is the cheapest item in this report. It is a lane, not a
redesign.

**Status correction.** The task brief says a lane (X4b) is repairing this. At
this tip it is not repaired. `wt/x4b-effectid` and `wt/x4-effectid` both point
at `e442a02`, the review merge, and contain no repair commit. `_s09_effect_id`
at `trajectory.py:257` is the synthesized form. Treat the causal half as open.

---

## 3. Candidates considered and rejected

Three candidates did not survive the "structural, not unfinished" test. They are
named so the orchestrator knows they were considered.

**The output budget was the ledger's bottleneck 2, and it is falsified on this
tree.** Lane B17 measured it four ways and the current ledger text is wrong.
The ledger (`:57-64`) says the route "answers in prose at a served 2048-token
budget" and that "no response at the frozen budget could have carried the
authored policy", citing 22734 characters against a 7000-character limit. B17
falsified the inference:

| ledger claim | B17 measurement |
|---|---|
| 7000 is the loader's acceptance limit | it is a constant in B12's driver (`invr1b12_swe_construction.py:192`); `verify_step_source` has no length rule at all and admits 22734 bytes and a 115-byte policy |
| no response at the budget could carry a working policy | a policy that **repairs 3 of 9 dev instances** is 5725 characters / 1378 tokens, fits 2048 with 670 to spare (`reports/evidence/invr1b17-budgetfit/budget-fit.json`, `verdict.c_protocol_asked_for_more_than_the_budget_carries`) |
| the budget is the binding constraint | falsified; the cause is prose-not-code, 3 of 3 responses |

The ledger's *observation* is true: 3 of 3 responses were prose with
`stop_reason: length`. Its *inference* is not, and it is stated as a bottleneck
whose fix is "cheap to test next". The cheap test was run; it came back
negative. The remaining live question is a route-and-protocol question, not an
architectural one.

**Even B17's own finding is thin where the ledger reads it as firm.** B12
acquired 0 of 4 lineages, and the ledger calls that a rate. Recomputed from
`reports/evidence/invr1b12-swe/store-rows.json`, the five operations were
**1 read timeout (`unknown`), 3 HTTP 502 failures, and 1 success**. So the
"acquisition rate is zero" claim rests on **one** returned artifact. B17 added
two more prose responses. The honest denominator for the current acquisition
disposition is three responses, all prose, none a policy. That is a route
observation with n=3, not a rate with n=25.

**The comparison instruments are unpowered** is folded into bottleneck 1 rather
than counted separately, together with the scripted crossing order. It is the
same constraint read from the panel side, and counting both would pad toward the
cap. The crossing order at `twodomain.py:339` and `:348` is a literal tuple, and
`"entered": "first"` / `"entered": "second"` are literals in the returned dict
(`:354`, `:366`), with `improvement_mode="operate"` and
`frontier["acquisition"] = "not-attempted"` (`:390`, `:397`). A frontier with
nothing selectable and a fixed order cannot demonstrate selection, so the
missing capability and the missing power are one bottleneck seen twice.

---

## 4. What is NOT a bottleneck, stated so it is not re-argued

These are real and they are not structural. None of them is in the list above.

**Fixed defects.** The freeze gap (a revision writing a frozen field through
`dict.update`, `|=`, `pop`, `clear`) was a defect and is repaired: `4b8ff03`
replaced the boolean `_attempts_frozen_write` with `_frozen_write_reason`
(`improve_channel.py:1258`) and rewrote the false promise in the
`admit_revision_under_freeze` docstring, which now correctly describes the
runtime comparison as guarding admission itself rather than as a backstop that
catches what the AST scan cannot. The concurrent-amend lock is likewise repaired
(`3a29b3c`). Seven production defects are now fixed across the batch.

**Unfinished work, not constraints.** `c4-live` never ran and
`b5-sealed-state` never ran. Neither consumed a dispatch. The inheritable
construction procedure exists and is eligible; nothing was attempted against it.
That is an unrun experiment, not a limit on what the system could establish. It
is correctly recorded as outstanding and it is excluded here.

**Free-route instability.** B12's three 502s and one timeout at a 300s deadline,
and B11's 4096 read timeout, are external-dependency observations about one free
route. They bound what one campaign measured. They are not a property of the
design.

---

## 5. The remaining gap, stated plainly

Only one candidate in this report is both architectural and cheap:
bottleneck 2, the synthesized effect identity, and it is inside the current
architecture. Bottleneck 1 is genuinely architectural and genuinely expensive: it
needs new instrument families, not new code.

That is unflattering to the batch's own framing, which ranked "the acquisition
rate is zero" first on the grounds that one number gates three dispositions. It
does gate them, but it is a **consequence**, not a constraint. The constraint is
that the comparisons cannot be expressed. A different acquisition rate would not
make the two-domain question askable while the Boolean side offers one
hypothesis class.

---

## 6. How to tell a bottleneck from the other two

- A **defect** is wrong at a place. It has a location, a reproducing case, and a
  repair. Seven of this batch's findings were defects. They are done.
- A **bottleneck** is a property of the shape. More engineering at the same shape
  cannot remove it. Both items above survive that test.
- A **shortfall** is a count that ran out. Unspent authorisation, a cancelled
  sweep, an unrun lane. These bound what a campaign measured and say nothing
  about the design.

A test for the distinction: ask whether the claim is *unanswered* or
*unaskable*. Unanswered means the study is unfinished. Unaskable means the
apparatus cannot express the comparison, which is what bottleneck 1 is, and what
bottleneck 2 is at the two arrows it covers.