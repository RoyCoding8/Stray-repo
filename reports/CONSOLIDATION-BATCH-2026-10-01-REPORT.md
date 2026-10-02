# Consolidation batch 2026-10-01: final report

Branch `codex/stage09-consolidation-2026-10-01`. Base `70223fb`. The tip this
report was written against is **`0deff30`**, and every count below was derived
at that commit with `git rev-list` unless the line says otherwise.

**How to read this file.** This is the report a reader should trust to describe
what happened. Where a source document and the tree disagree, the tree won and
the disagreement is recorded here rather than smoothed over. Where a number in
the brief I was given was stale, I derived the number and said so. Where I could
not verify a claim, I say that instead of assuming it.

Three findings in the record that the current status documents do not carry are
in §11. One of them changes how the mechanism result should be read.

---

## 1. What was asked, and what this report concludes

Milestones A, B and C, delivered as one integration branch, with the ledger,
roadmap and completion matrix updated and no more than three
architecture-relevant bottlenecks recorded.

| Milestone | Goal | What the evidence supports |
|---|---|---|
| A | Close the causal path from permitted experience to fresh-process use, under tamper | **Closed on both halves of the mechanism, after an overturn.** The freeze and the effect identity were both over-claimed and both repaired. One further finding, uncited anywhere in the status documents, bounds what "closed" means. See §3 and §11.1 |
| B | Finish an informative two-structure comparison with a frozen panel and sealed assessment | **Not achieved.** Acquisition, utility, transfer and improvement are negative. The comparison is not merely unanswered, it is unaskable at this alpha on these instruments. §4, §6 |
| C | Connect inherited learning to Stage 10 | **Mechanism built, never exercised.** The inheritable construction procedure exists and is eligible. Nothing was attempted against it. §7 |

**The one-line conclusion.** The batch made the mechanism real and honestly
bounded, found and repaired roughly fourteen production defects, and produced no
evidence on any learning question. Four of the five dispositions are negative and
the fifth is not established, and the reason the learning questions cannot be
answered is structural rather than unfinished: the design supplies one
independent unit of variation per structure, so a contrast on it is n=1
however many rows it runs.

---

## 2. What a reader may rely on

This section is the load-bearing part. Everything else is detail.

**You may rely on the mechanism result, with the bound in §11.1.** The chain's
rows are durable, the freeze refuses every mapping-method write form tested
against it, and the effect identity is now read off a settled `operations` row
and checked against the database before it is written. Two independent passes
disagreed about this and the disagreement is resolved in favour of the
repair.

**You may rely on the negatives, and on their denominators.** Every figure in
§4 was recomputed from the evidence directories at `0deff30`, not taken from a
lane summary. The acquisition denominator is one returned artifact. The
retention leg never put retention under pressure at all. Both are stated with
their limits attached, which is why they can be trusted.

**You may rely on the standing reds.** Each is a finding with a reason, not
loose work. §9.

**You must not read the mechanism result as evidence for any learning claim.**
The status documents are careful about this and so is this report. A closed
causal path tells you the plumbing works. It says nothing about whether the
system learns.

**You must not read the bottleneck count as the record of what blocks
research.** Two bottlenecks survived and one of them was falsified after the
ledger named it. §8.

**Where this report contradicts the status documents, it is because I derived a
number or read source.** §11 lists all four places that happened.

---

## 3. Established: the mechanism, and how it nearly was not

The honest account is that the mechanism was **not** established when it was
first claimed.

### The first verdict and its reversal

An independent acceptance pass (`reports/FINAL-ACCEPTANCE.md`, merged at
`8a207ab`) returned mechanism **CONFIRMED**. A later independent reviewer
(`reports/workstreams/r-final-review.md`, merged at `e442a02`) overturned it to
**too generous**, on two defects. The acceptance pass's numeric layer held up
under re-derivation; what it did not reach was the freeze and the causal join.
The reversal is part of the record and not a footnote.

The acceptance pass had also probed the freeze with 19 binding forms it wrote
itself and found zero mismatches. That probe was sound and the number was
right. All 19 forms were subscript or attribute spellings, so the mapping-method
forms beside them were never asked about. A probe bounds what it probed.

### Defect one: the freeze admitted a write through a mapping method

The freeze declared `FROZEN_FIELDS` but enforced only `ast.Assign` and
`ast.AugAssign`. A frozen write expressed as `view.update({"grant": x})`, or
`|=`, `pop`, `clear`, or `popitem`, passed the guard while still writing the
field at runtime.

The reviewer demonstrated this end to end. A revision smuggled
`(view.update({"grant": {...}}) or 3)` into its probed-input expression was
admitted as `eligibility: eligible`, `informs_decision: True`, and executing it
overwrote the grant.

The credit given to a second layer, the runtime before/after comparison in
`admit_revision_under_freeze`, **could not fire.** A revision's bytes run out of
process against a JSON view that carries none of the six frozen fields, and the
store being compared is never in the child's reach. The two sets are disjoint.

**The repair (lane X3, merge `6afd724`).** The node-type enumeration was replaced
with the parse's own binding contexts, and the key-taking and keyless method
forms were added. Verified at `0deff30` by reading the source:
`_attempts_frozen_write` is at `improve_channel.py:1220`, its write-position
test is `isinstance(node.ctx, (ast.Store, ast.Del))` at line 1329, and
`_KEY_WRITING_METHODS` at line 1414 is
`frozenset(("update", "setdefault", "pop", "popitem", "clear", "__delitem__"))`.
Unresolvable keys and unreadable mapping arguments are refused rather than
admitted.

The helper whose docstring promised a runtime backstop that could never fire
was **deleted rather than annotated.** I verified `_frozen_key` has zero
occurrences in `improve_channel.py`. The surviving comparison now says only what
it holds. Line 1279 reads "There is no runtime backstop and this function is the
whole of the freeze."

### Defect two: the effect identity named no row

`s09_policy_state.effect_id` was written as the constant
`ad01-<cid>-b<seq>-effect`. That string named no `operations` row and was read
back by nothing. The admitted-effect to observation arrow was durable on both
sides and joined only by `(investigation_id, seq)`.

This is structural rather than incidental. `attempt_observations` is
`(id, attempt_id, content, created_at)` and has no `operation_id` and no
`effect_id` column at all. The reviewer measured it against real PostgreSQL: 3
of 3 synthesized ids absent from `operations`, and no observation carrying
either field.

**The repair (lane X4b, merge `423772f`).** Verified at `0deff30` by reading
`trajectory.py:257-314`. `_effect_operation_id` reads the operation id off the
episode, then checks it against `SELECT id FROM operations WHERE id = ANY(%s)
AND settled` **before** the value is written. An episode can carry any string,
so trusting the episode would make the column true by being written to. The
database has the last word. `_s09_effect_id` at line 305 is now a reader.

**The limit, stated honestly.** A boundary that runs a host-side diagnostic
admits no operation at all, and there the row carries an empty identity. That is
a true answer rather than a fallback, and writing a synthesized id there would
restore exactly the defect.

### The arrow count

The documents disagree here and I could not resolve it from the tree.
`r-final-review.md:135` says four of the seven arrows were causally bound at the
time it reviewed. The ledger says five, counting the repair. Both describe their
own moment. The honest statement is that the mechanism now rests on the repairs
being real, and the repairs are verified above.

---

## 4. Negative, and staying negative

Every figure here was recomputed from the evidence directories at `0deff30`.

### Acquisition: 0 of 4 lineages, resting on one returned artifact

From `reports/evidence/invr1b12-swe/campaign.json`, under its `summary` key:
`acquired_lineages` 0, `no_acquisition_lineages` 4,
`lineages_attempted` 4, `distinct_acquisition_digests` 0.

From `reports/evidence/invr1b12-swe/store-rows.json`: 5 operations, 5 receipts,
reconciled one to one. **What the five were is not five attempts at the same
thing.** I counted the receipt outcomes: 1 `unknown`, 3 `failure`, 1 `success`.
The `unknown` is `error_kind: timeout`, `response_class: lost-response`,
`response_received: false`. Three carry `http 502` with `response_status: 502`.

Exactly one artifact was ever returned. B17 added two further sends; both were
prose and neither opened a step definition
(`responses_returned` 2, `responses_opening_a_step_definition` 0).

**The honest denominator is one observation, not a rate.** "0 of 4 over 25
authorised sends" is not a rate and the ledger previously read it as one. B12
spent 5 of 25, leaving 19 unspent.

### The served budget, and the inference that was wrong

Verified rung by rung in
`reports/evidence/invr1b11-budget/budget-probe.json`. Six authorised sends, all
six spent. Rungs at 16, 64, 256, 1024 and 2048 each return HTTP 200 with
`stop_reason: length` and an output token count exactly equal to the rung. The
4096 rung has no `stop_reason`, `dispatch_state: unresolved`,
`response_received: false`, reason "gateway read timed out", at a 300000 ms
deadline. A token-limited response and a lost response are different facts and
the record keeps them apart.

The status documents previously named the output budget as the binding
constraint and inferred that no response at that budget could carry a working
policy. **That inference was falsified four ways by B17**
(`reports/evidence/invr1b17-budgetfit/budget-fit.json`), and I verified each:

- 7000 is not a loader limit. It is `MAX_SOURCE_CHARACTERS`, a constant in B12's
  own driver. `verify_step_source` has no length rule and admits the authored
  control's 22734 bytes and a 115-character policy.
- A policy repairing 3 of 9 dev instances is 5551 characters
  (`offline_measurements.compact_repairing_policy.characters`) and fits the
  served 2048-token budget with room to spare.

The corrected reading: all three returned responses were prose from their first
byte, so no continuation of them was ever going to become a policy. The
truncation is why the cause was never observed to end. It is not the cause. The
remaining live question is a route-and-protocol question, not an architectural
one.

A conflict inside the evidence file is recorded rather than resolved: the same
record's prose sentence says 5725 characters where the measured field says 5551.
The field is the measured one and both clear both limits, so no disposition
turns on it.

### Retention: 0 of 3 members over 27 executions

From `reports/evidence/invr1b14-retention/retention.json`: 3 live-acquired
members, each with `acquired_from_provider: true`, a real `operation_id`, and
`distinct_verdicts: ["preserved"]`. The lane's own verdict block reads
`live_acquired_measurable: 0`, `strategy_measurable: 0`, `routable: false`,
`measured_live: false`.

**Retention was never at risk, so it cannot be distinguished from doing
nothing.** This is an instrument-degeneracy observation and the matrix records a
bare NEGATIVE without it. The reason is in source: the returned candidate is
either the whole task or a `keep` the oracle already graded `preserved`, so the
verdict axis has exactly one reachable value. Nothing was ever removed. I
verified this myself and the third acceptance pass found it independently.

### Utility, transfer, learner improvement

All negative. Utility is not measurable at all: there is no learned arm,
because a failed acquisition is never promoted to an authored substitute.
Transfer has two independent zeros. Learner improvement is negative because
`c4-live` never ran, so no eligible revision was attempted and no revised
descendant cohort exists.

### The governed budget

B11 spent 6 of 6 authorised. B12 spent 5 of 25, leaving 19 unspent. B14 spent
0. Unknown stayed unknown: `billed` and `charge_units` are null on every receipt
from this route, and the lost send records `input_tokens: "unknown"` rather than
zero. Carried-in historical exposure of at least 5563 units is accounted
separately and was never netted against the fresh allocation.

---

## 5. What was refuted outright

**The output-budget constraint, as a bottleneck.** Measured and falsified by B17
after the ledger named it. Recorded as a corrected inference, not a
bottleneck.

**The "0 of 4 over 25 sends is a rate" reading.** The denominator is one
returned artifact.

**The 19-form freeze probe as evidence of freeze coverage.** It was sound and it
bounded what it probed.

**Three briefs written by the orchestrator.** Six in the earlier pass, recorded
in `reports/STAGE-09-HANDOVER.md:305-315` in the orchestrator's own table, and
several more in this batch. §12.

---

## 6. Autonomous frontier selection: not established

The crossing runs a fixed three-then-three sequence written into
`experiments/ad01/twodomain.py`. `"entered": "first"` and `"entered": "second"`
are literals in the returned dict, `improvement_mode` is the constant
`"operate"`, and `frontier["acquisition"]` is the literal `"not-attempted"`. No
frontier is consulted and no candidate is chosen. A script is not a program
choosing from the admissible frontier.

**Read per split, the crossing is unpowered on both sides.** I verified this by
running the census, not by reading it:

- Boolean side: I generated all 3 splits x 24 seeds and collected the
  `hypothesis_class` descriptors. **Exactly 1 distinct descriptor** across 72
  tasks, against 6 required. The descriptor is byte-identical every time:
  `class_digest 285113caf4ab`, `class_size 224`, `n_inputs 4`, `n_outputs 4`.
  The 72 tasks carry **72 distinct hidden truth tables**, drawn from one class
  of 224. The tasks differ and the class does not.
- SWE side: `twodomain.py:126` returns
  `len(set(DEV_TEMPLATES) | set(HELD_OUT_TEMPLATES))`. I read the constants:
  `DEV_TEMPLATES` holds 3 and `HELD_OUT_TEMPLATES` holds 6, so the union is 9
  and `powered: True` is declared. **Per split that is 3 or 6 against 6
  required.** Dev is unpowered, held-out is exactly at threshold with zero
  margin, and the union clears the bar through the very census the split exists
  to prevent. The crossing then spends 2 dev episodes and 1 held-out.

I also recomputed the frozen panel census at
`reports/evidence/invr1b8-panel-census/census.json`: 14 panels, cluster rule
`(family, template)`, **exactly 3 powered and all three graph-only** at 6
against 6. All 7 software panels are unpowered, the largest reaching 4 against 6.

**Panel power is a repairable defect. The independent-unit deficit is not.**
A panel choice fixes the first; the second needs six different generators.

---

## 7. Milestone C: built, never exercised

**Real and verified.** `migrations/0019_mission_entry.sql` adds six columns to
the `investigations` row that already owns investigation identity rather than
creating a new table, and `mission.py` refuses a seventh mission key. C1 retired
the partial owners and C6 gave resume a single owner that names what it resumed.
C4 deleted the fixed two-member menu, so `reachable_evidence` is now a function
of the program rather than a constant published beside it, and `_revision_source`
returns ~1067-character sources that pass the frozen-write check.

**Not reached.** `c4-live` never ran, and `b5-sealed-state` never ran. Neither
consumed a dispatch. The inheritable construction procedure exists and is
eligible. Nothing was attempted against it, so nothing here claims beneficial
RSI, and Stage 10 remains prototype level.

**One clarification the third pass forced.** The claim is that the acquisition
*procedure* is inheritable and revisable. It is inheritable. It is not
revisable: `construction_from_evidence` is a module-level function hard-coded to
return the last spent input, and nothing in the revision interface reaches it.
The procedure can be inherited and used. The procedure cannot yet be changed.

---

## 8. The two bottlenecks

The assignment permits no more than three. Two survived, and the cap was a
maximum rather than a target. Full argument in
`reports/workstreams/bottlenecks.md`.

### 1. No independent unit for any learning claim

Every disposition above acquisition compares two arms, and the design supplies
one independent unit of variation per structure. A contrast is n=1 however many
rows it runs. The system cannot express the comparison it is trying to make, so
the question is not unanswered. It is unaskable at this alpha.

The Boolean hypothesis class is a published constant carried by construction, so
no panel choice over existing tasks moves it. Going from 1 unit to 6 needs six
different generators.

This blocks task utility, learner improvement, and any two-domain claim.

### 2. The chain's effect identity was synthesized, so two arrows were bound by position rather than by cause

Repaired by X4b. What survives is the lesson rather than the defect: the proof
the batch relied on was the existence of rows, and the causal binding was tested
by nothing, so it would have kept proving the weaker thing after every other
defect in the tree was fixed.

### Not bottlenecks, stated so they are not re-argued

Fixed defects: the freeze gap, the concurrent-amend lock, the migration-count and
menu-test migrations. Unfinished work: `c4-live` and `b5-sealed-state` never ran,
which bounds what a campaign measured and says nothing about the design. Free-route
instability: B12's 502s and timeout are external-dependency observations about
one route.

---

## 9. Production defects found and repaired

Roughly fourteen, across two search passes, an independent review, a third
acceptance pass, and the red audit. The recurring shape was **a lock taken on a
row the writer may not have created, or a read and a write split across two
connections.** That shape produced most of them.

| # | Defect | Where | Repair |
|---|---|---|---|
| 1 | Lost hold on `investigations.in_flight` across two connections | `mission.py` | `FOR UPDATE`; the read-then-write replace is gone |
| 2 | A **fourth writer** of `in_flight`, same class as #1 | three call sites | same barrier, verified at all of them |
| 3 | `AnnAssign` / `NamedExpr` reached a frozen write | freeze guard | refused; later subsumed by the parse-context rewrite |
| 4 | `take_correction` locked a row the writer might not have created | `authority.py` | insert the zero row `ON CONFLICT DO NOTHING` **before** the `FOR UPDATE`, making the conflict itself the lock |
| 5 | `amend_protocol` read on one connection, committed, wrote `supersedes` on a second with autocommit; four concurrent amends of one parent all applied | `src/settlement/trials.py` | X5 holds the parent `FOR UPDATE` and inserts the child in the same transaction. The refusal raises rather than returning a `CommandResult`, because `store.transact` converts a raised error into a returned one and two live callers ignore the returned result |
| 6 | The freeze admitted a write through a mapping method, and credited a second layer that cannot fire | `improve_channel.py` | X3, §3 |
| 7 | The effect identity was synthesized, binding two arrows by position | `trajectory.py` | X4b, §3 |
| 8 | The migration count was pinned as the literal 18 while the tree carried 20 | `test_s09_run_isolation.py` | `expected_migrations()` reads the same glob `apply_migrations` reads |
| 9 | The three-call-site authority mandate was migrated in one file and left in place in three others | `test_m1_shared_executor.py` and others | MIG-MIGRATE |
| 10 | A reader census gate excluded any path containing `.worktrees` while deriving its root from `__file__`, so inside a lane worktree it was green and blind | `test_c14_live_already_spent_source.py` | C14-FIX replaced the exclusion with a structural root resolution |
| 11 | Four tests asserted the deleted two-member menu | two test files | SIB-FIX, SIB2-FIX |
| 12 | The decoy's justification was wrong, and removing the decoy would have been the wrong repair | DECOY-FIX | repaired the justification |
| 13 | A guard counting 26 `OTHER_WRITES` entries that are 25 distinct | `test_inv_x2_subscript_freeze.py` | recorded, §9 |
| 14 | Six guards whose subjects had been repaired stayed red | `test_inv_z2_red_audit.py` | Z2-RETARGET re-aimed all six rather than deleting them |

**One cause was not a stale test.** `lineage_descendant_score` now substitutes
the probed input, so the archived artifact names best probe 0 where a live run
of the identical call names 7. That drift predates this batch and is
irreducible, because `reports/evidence/` is immutable. The test now pins what is
checkable and fails if the menu ever returns.

**One number changed rather than being pinned.** Migrating two tests made panel
cells execute instead of being refused, which changed the cost: the production
revision spends 8, not the pinned 16. The old figure was one the panel never
actually spent. The migration count is now read from the same glob rather than
restated.

---

## 10. Standing reds, and why they stand

**FA-04** asserts `hasattr(channel, "REACHABLE_EVIDENCE")`. I verified that name
is absent from `improve_channel.py` and present in the archived generator at
`reports/evidence/inv_r1_e4/make_evidence.py`. The correct deletion of the fixed
menu falsifies the assertion, and it can only be greened by restoring a menu
that milestone C deliberately deleted. It is a record of a correct repair.

**FA-02** names `reports/evidence/invr1b4-mean-score/b4-crossover-mean.json`. I
verified both that the file and its parent directory are absent from this tree.
The one `control_competence(40)` sweep was cancelled for resource reasons, and
the artifact must not be fabricated to satisfy a gate that reads it.

**A guard counting 26 entries that are 25.** `OTHER_WRITES` in
`test_inv_x2_subscript_freeze.py:240` has 26 list entries and 25 distinct strings.
`'if (grant := {"queries": 99}): pass'` appears twice, at lines 205 and 211, so
the parametrized test collects 26 test ids for 25 distinct positions. A reader
counting 26 green tests reads 26 covered. 25 are covered and one runs twice. I
verified this by parsing the literal.

**A substring guard satisfied by its own docstring.** The RF-02 mechanism record
asserts the string `"operations"` appears in the source of the function that
derives the effect identity. That function's name appears three times: twice in
its docstring and once in the SQL. Deleting the query and leaving the prose
passes the guard. It cannot distinguish *asking* the table from *documenting*
that it asks it.

**Nine tests that fail on an authority refusal, on purpose.** The mandate from
`1e0dd44` was migrated in the one file the original guard watched and left in
place in three others. The re-aimed guard now scans all nine sites, including
two policy steps written into a `subprocess` probe's source string, which a
`Call`-node scan sees only as a `Constant`. A guard reading `Call` nodes would
count seven of nine and would be trusted for the two it missed.

**One batch with no verdict.** `tests/test_s09_swe_experiment.py` ran 7 of its
57 tests before being stopped, on a CPU and thermal budget. The remaining 50 are
unmeasured. Three attempts were killed by their own timeouts. This is recorded
as a gap and not as a pass.

---

## 11. Where this report contradicts the status documents

Four places. In each the tree won.

### 11.1 The freeze has no production caller, and no status document says so

This is the finding that matters most and it is not in the ledger, the matrix,
the roadmap, or the bottleneck document.

`admit_revision_under_freeze` is the only path that reaches
`_frozen_write_reason`. Its sole non-test caller is
`experiments/ad01/learner_revision.py:572`. `learner_revision.acquire` has no
non-test caller either: its only in-module callers are `_admit` and `_run_one`,
both reached only from `learner_revision.run_campaign`, and the five
`run_campaign` call sites elsewhere in the tree resolve to four different
functions of that name. I checked each by AST rather than by name.

Meanwhile the chain that actually executes a model's improver bytes runs
`verify_step_source` and nothing else. I read `run_improve_step`,
`drive_improve_round` and `_run_source` and none of the three mentions
`_frozen_write_reason`, `_attempts_frozen_write`, `classify_revision` or
`admit_revision_under_freeze`.

**What this does and does not mean.** The guard is real and its hole is
genuinely narrower than it was, so this is not a regression from X3. What it
means is that on the live acquisition path the freeze is a function that tests
call, not a gate the running system passes through. Seven places describe it as
enforced without that bound, and all seven overstate it:

- `reports/PROJECT-LEDGER.md:45` lists "a freeze enforced against the parse, not
  a hand-kept list" among what the batch established.
- `reports/PROJECT-LEDGER.md:160` and
  `reports/STAGE-09-10-COMPLETION-MATRIX.md:282` both record a **Keep**
  decision for "the enforced freeze and its refusal suite".
- `reports/STAGE-09-10-COMPLETION-MATRIX.md:80` marks the row "Freeze enforced
  against the parse" as `confirmed` after X3.
- `docs/design/REFINEMENT-ROADMAP.md:32` repeats the phrase.
- `reports/FINAL-ACCEPTANCE.md:39` lists "an enforced freeze" among what the
  batch established, and line 71 reads "The freeze is enforced against the
  parse, not a hand-kept list".

The matrix's own reading rule says a row is `completed` only where a named
artifact carries the claim. The claim that the freeze gates the running system
has no artifact, because no production path consults it.

Two related findings from the same pass, unadopted anywhere:

- Three write forms are admitted as `eligible` through an alias the guard does
  not follow: a `for` target, a walrus, and a nested-function parameter. All
  three remove the frozen field when executed. **Currently unexploitable**,
  because the view the child receives carries none of the six frozen fields, and
  the driver reads back only the returned action. It becomes exploitable the
  moment the view carries a frozen field, which is the trigger the module's own
  docstring names.
- A tuple or list key inside `update` **raises** out of the guard instead of
  refusing. The module's stated policy is default-deny, and a raise is not a
  refusal.

### 11.2 A third acceptance pass exists and is cited nowhere

`reports/workstreams/final-accept.md` was committed at `dd410bf`, at 20:10 on
2026-10-01. I verified by ancestry that it postdates every repair: it is not an
ancestor of the X3, X4b, X5, MIG-MIGRATE, C14-FIX or DOC-APPLY merges. Its
verdict is three "not established" and one "established, with a stated limit".

`git grep` finds no citation of `final-accept` in the ledger, the matrix, the
roadmap or the bottleneck document. Its Finding 11.1 above, its Finding 7 on
constructor controls whose pass condition is a tautology, and its Finding 5 on
a prompt test whose name asserts an absence its own assertion contradicts have
no disposition anywhere.

Only one commit touched the files it names after it landed, and that commit is
GIVEAWAY at `b62b070`, which addressed a different finding. Its mechanism
findings are unrepaired.

### 11.3 The ledger, matrix and roadmap name a stale tip

All three say the batch stands at `5b7f1ca`. The tip is `0deff30`. The ledger's
figures of 129 commits, 52 merges and 47 lanes are correct **at `5b7f1ca`**, and
POLISH measured them there. I re-derived at `0deff30`:

- commits over base `70223fb`: **131**
- merges: **53**
- merges naming a lane: **48**
- distinct lane labels: **48**, none reused
- non-lane merges: **5** (the independent review, the delivery merge, the
  first acceptance pass, and the two search passes)

The 47 figure is a merge count that happens to equal the distinct-label count
because no label is reused. The figures are stale by one merge, not wrong.

### 11.4 The first acceptance pass still overstates, and the correction landed beside it

POLISH added a banner to `FINAL-ACCEPTANCE.md` saying its dispositions do not
govern, and corrected its headline counts. Two of its body statements survive
and both are now false:

- Line 109 still reads "This is a bounded zero resting on a rate". It rests on
  one returned artifact, not a rate.
- Line 84 still reads "The dynamic before/after comparison in
  `admit_revision_under_freeze` is the layer that catches it. The freeze is one
  layer deep, not two." That comparison cannot fire and was deleted as a
  promise.

### 11.5 A minor one

`c4-live` is recorded as having "no evidence directory". `evidence-ad01/c4-live/`
exists on this tree with 22 tracked files, 11 JSON and 11 logs, of which 3 are
zero-byte. Two different things are being called `C4`: lane C4 is the offline
inheritable construction procedure and has no live call, while that directory is
the AD01 live qualification directory. The honest fix is to disambiguate the two
names. I did not verify whether the AD01 aggregate spend respected its declared
bound: every readable trace records `charge_units: 0` and no receipt file
exists, so no breach is detectable and none is claimed.

---

## 12. The orchestrator's own errors

This section is the most useful part of the report for anyone running the same
process. Every item below was caught by a lane, not by the orchestrator noticing.

**Counts came from memory and were wrong, repeatedly.** "62 lanes merged" was
reported more than once. The true figure never matched it. The ledger carried
"221 commits, ~53 lanes"; `git rev-list --count 794737f` is 221 for the *whole
history*, not the batch, and no derivation of 53 lanes existed under either a
merge-subject count or a distinct-branch count. doc-delta could not reproduce
either figure and said so rather than adopting one. The corrected figures landed
only after POLISH measured them at a named tip.

**A root cause was asserted to three lanes and measurement contradicted it
each time.** The pattern repeats with different content. A lane was told 20
failures traced to one inherited cause and left them alone; a lane was told the
brief's invariance claim and measured it false, writing "The brief asked for
invariance to 'the number of identical rules' and asserted a mean over one world
equals a mean over three. That is false, and I had it written that way before
measuring it." A lane was told a symbol lived in one module and answered that
`git log -S` finds only a removal of the witness strings.

**A brief predicted a state and the measurement disagreed.** The red-audit
retarget brief "predicted four reds and two passes. The measured state is five
reds and one pass."

**A lane's own defect was described wrong.** One defect was reported to a lane as
green-but-blind when it was in fact red, and a root cause was attributed to a
deleted symbol when it was not deleted.

**A resource protection was reported as in place when it was inert.** `Set-Content
-Encoding utf8` writes a BOM, and WSL's parser silently ignored every key in the
resulting `.wslconfig`. **I could not corroborate this one in the tree.** No
report under `reports/` or `docs/` mentions `wslconfig` or `Set-Content`. I am
recording it because it was reported to me as fact and I have no reason to doubt
it, but it is uncorroborated here and a reader should know that.

**A dispatch was announced and not made.** This one turns up in the record as a
process failure rather than a claim, and I could not locate the transcript. It
belongs in the list because the pattern is the one that costs the most time: the
turn ends on a finding instead of on the call.

**A lane was never merged while its verdict was reported as though it were in
the tree.** The red audit's own report states it plainly: "This file was never
merged, so none of the above was visible to the tree until now." Its nine
unexplained reds were real and were invisible to everyone reading the status
documents.

**The earlier pass recorded the same class of failure in its own words.** Six
briefs contradicted by source, two lanes' mutations left live in the shared
tree, three lanes editing the main tree instead of their worktrees, and one
lane staging a file another lane owned. No cross-contamination reached a commit.
The handover's own conclusion is the rule: verify every lane claim against
source.

**The one that generalises.** The project keeps producing checks narrower than
the claims made from them. A guard that cannot fail, a `startswith` filter
admitting two live databases, a competence check covering one budget while the
report claims all of them, an `OTHER_WRITES` list with a duplicate in it. A check
narrower than its claim is worse than no check, because a reader who follows the
citation finds green and concludes the claim holds. Three of the standing reds
in §10 are instances, and the freeze's production-caller gap in §11.1 is a
fourth.

---

## 13. Documentation drift, and what was done about it

The ledger, roadmap and matrix all claimed the mechanism settled when it had
been overturned. All three were corrected by DOC-APPLY, and doc-delta's analysis
of what was wrong is in `reports/workstreams/doc-delta.md`.

**Twelve historical records were given a pointer rather than rewritten.** I
verified by diffing the POLISH merge against its first parent: it touched 17
files, of which 13 are historical status documents that each received a
supersession pointer, plus the ledger, the matrix, the roadmap and the first
acceptance pass, which received corrections. No historical record was rewritten
and nothing under `reports/evidence/` was touched. AGENTS.md requires historical
reports to describe their own revisions, and that holds.

**Evidence immutability holds.** I verified at `0deff30`: over the whole batch,
`git diff --name-status 70223fb..HEAD -- reports/evidence/` returns **10 additions
and zero modifications, deletions or renames**. Same for `reports/cap-sheets/`,
which shows 2 additions. No commit in the batch touched an existing evidence
file. The two archived generators that still reference deleted names are recorded
in the matrix rather than annotated in place, because adding a file to an
archived evidence tree is the first step toward editing one.

**One claim was falsified and the inference corrected.** The output-budget
inference, §4.

**One lane count matched no computable figure** and was corrected at a named tip,
though the tip it names is now one merge stale, §11.3.

---

## 14. Outstanding

| Item | State | Why it is not closed |
|---|---|---|
| `c4-live` | never run | The milestone-C deliverable. The mechanism exists and is eligible; nothing was attempted against it |
| `b5-sealed-state` | never run | Per-task policy state in sealed assessment |
| B4 crossover | unmeasured | The one `control_competence(40)` sweep was cancelled before it returned. A cancelled measurement is not a null measurement |
| Acquisition | open | 0 of 4 on one returned artifact. The output budget is not the constraint; the remaining question is a route-and-protocol one |
| Two-domain comparison | not askable | One independent unit per structure, and a fixed episode order |
| Freeze enforcement on the live path | open | §11.1. The guard has no production caller |
| `tests/test_s09_swe_experiment.py` | unmeasured | 7 of 57 completed |
| Remote equality | **not done** | See below |

**Remote equality is outstanding.** The assignment asked for a push and verified
remote equality, and it has not happened. The local tip `0deff30` is **6 commits
ahead** of `origin/codex/stage09-consolidation-2026-10-01`, which sits at
`2c33320`, and the local branch is 0 behind. I was instructed not to push, so
this is reported rather than fixed. Anyone treating the remote as the delivered
state is six merges short.

---

## 15. Base and method

Every figure in this report was derived at `0deff30` from the tree, not taken
from a summary. Counts came from `git rev-list`, `git log --merges`, and
`git merge-base --is-ancestor`. Evidence figures came from parsing the JSON in
`reports/evidence/` directly. The panel census, the Boolean hypothesis-class
count and the SWE template counts were recomputed by running the code. The
freeze call graph, the effect-identity repair, the amend-protocol repair and the
`OTHER_WRITES` duplicate were verified by reading source and by AST walks rather
than by grepping names.

Where I could not determine something, I said so. The three items are the arrow
count in §3, the `.wslconfig` claim in §12, and the c4-live spend bound in
§11.5.

Nothing under `reports/evidence/` was edited. No history was rewritten. No push
and no merge.
