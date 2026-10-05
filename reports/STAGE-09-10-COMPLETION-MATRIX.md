# Stage 9–10 completion matrix — consolidation batch 2026-10-01

Current checkpoint: the [2026-10-04 mission-ownership batch](PROJECT-LEDGER.md#mission-ownership-and-instrument-census-2026-10-04)
at `ff5b767` over `0ee4699`. The six dispositions below are updated from that
batch. **No lane in it ran a test suite**, so its behavioral claims are static
arguments from source, probes against frozen artifacts, or arithmetic on an
existing CI log. The earlier checkpoint, the
[2026-10-03 researcher review](PROJECT-LEDGER.md#researcher-review-and-surgical-closure-2026-10-03),
kept stages 9/10 incomplete; nothing since has closed that.

The 2026-10-04 batch changed two things that bear on the dispositions. The five
write-only mission columns are gone (`migrations/0021`), so the public mission
no longer carries a projection nobody reads; what remains is that the two
investigation rows are not the same row. And M3's supported-cell count is
**zero, measured**. Neither reaches utility, transfer or learner improvement.

The tables below retain the older studies' scoped dispositions; no historical
disposition has been softened, and the current ledger distinguishes the public
A42 instrument from the worker's separate fixture pilot.

The current completion report for the consolidation batch
`codex/stage09-consolidation-2026-10-01`, first integrated at `8a207ab` from
`70223fb`, reviewed and repaired at `8cc1927` after an independent review
overturned its mechanism verdict. The current source review is `a7c132c`,
recorded in [PROJECT-LEDGER](PROJECT-LEDGER.md#coordinator-review-2026-10-02).
Later surgical repairs are recorded in the ledger's current closure section;
they do not change the acquisition, benefit, integration or stage dispositions.
Canonical source is now `codex/agent-society`; original revisions are archived.
This file maps requirements to inspected evidence.

**Relationship to the other matrices.** This file does not replace
[`STAGE-09-COMPLETION-MATRIX.md`](STAGE-09-COMPLETION-MATRIX.md), which is not
edited. That file carries an explicit banner declaring itself historical and
non-governing, and it argues from symbols this batch deleted; it describes its
own source revisions, which `AGENTS.md` requires be preserved.
[`STAGE-09-CONSOLIDATION.md`](STAGE-09-CONSOLIDATION.md) is an older branch's
handback and stays where it is. This file is the current one.

**Reading rule.** A row is `completed` only where a named artifact carries the
claim and the artifact was read. A lane's report is a claim, not a row. **A
negative valid study completes its question. An unrun study does not.** Where a
report and its own artifact disagree, the artifact decides.

**Vocabulary.** `confirmed` — the mechanism does what it claims, probed against
source. `negative` — the question was asked and the answer is no, with real
provenance. `not measurable` — the question's input arm does not exist, so no
answer was obtained and none is implied. `not established` — the demonstration
is not the claim. `never run` — no report, no evidence directory, no test.
`over-claimed` — the mechanism does not do what the report said it did, so the
mechanism is not credited with it. `not established` covers a demonstration
that fell short of a claim; `over-claimed` covers a claim the demonstration does
not reach at all.

## 0. The six dispositions

This section and the current ledger govern the 2026-10-02 assessment. Detailed
rows below retain the worker's earlier scoped inventories and named revisions;
this review did not rerun every gate or endorse every historical disposition.

Each is the independent acceptance pass's own verdict. They are kept separate
because the first does not license the rest.

| # | Question | Disposition | One line of why |
|---|---|---|---|
| 1 | Mechanism | **SCOPED QUALIFICATION**, with the mission projection now gone | Durable effect identity and mandatory execution authority remain repaired. As of `ff5b767` the public mission no longer carries five columns nobody read, and the live path refuses to execute a round on a store that names an owner. SQL and JSON mission ownership are still separate, and no test suite has run since `0ee4699`. The two real-database scorer checks above belong to the 2026-10-02 review tree and this batch neither reruns nor retracts them. |
| 2 | Acquisition | **OBSERVED NO ACQUISITION** | Unchanged. B12 acquired 0 of 4 scheduled lineages, with only one returned artifact among five operations. Transport failures do not measure model capability. The 2026-10-04 batch attempted no acquisition. The route is live on this host (a process answers on `127.0.0.1:4000` with `401 invalid api key`); this session holds no credential, so no send was made. |
| 3 | Utility | **UNMEASURED** | Unchanged. No usable acquired arm exists in this comparison, and the batch created none. No benefit verdict follows. |
| 4 | Retention/transfer | **UNMEASURED BENEFIT** | Unchanged. B14 found a constant reachable terminal verdict. This diagnoses the instrument; it does not test whether retained competence can help. Dropping the write-only `retained_use` column removed a claim, not a measurement. |
| 5 | Autonomous selection | **NOT ESTABLISHED**, and one of its two known causes is repaired while the other blocks it | The five mission columns are dropped, so "the public mission writes summaries nobody consumes" no longer holds. What blocks it now is row identity: the live arm and the campaign mint different SQL rows, so the SQL quiescence predicate has no production caller and two predicates remain. `twodomain.run_two_domain_crossing` also no longer writes a mission row at all, having zero production callers. |
| 6 | Learner improvement | **LIVE STUDY UNRUN** | Unchanged. Live C4 and its fresh-descendant comparison did not run. **Its existence does not claim beneficial RSI**: no eligible revision ran, so no learner improved. Executable probe selection can influence descendants, but benefit is unmeasured. The earlier "not runnable on this host" clause was wrong and is withdrawn; the route is live and this session holds no credential. |

**What the 2026-10-04 batch measured, as new rows.**

| Measurement | State | Evidence |
|---|---|---|
| Mission projection | **`measured`. Five write-only columns dropped | `migrations/0021` removes `frontier`, `permitted_experience`, `active_program`, `acquired_artifacts`, `retained_use`. No production reader existed for any of them; `retained_use` had no writer either. Forward migration, not an edit to `0019`, because `apply_migrations` records file names in `schema_migrations`. |
| Execution authority on an owned store | **`confirmed` as a source argument, unrun** | `drive_improve_round` refuses `authority=None` when `store.identity` is set. The production live path passed none, so a database was created and dropped per round. `_disposable_authority` still serves nameless fixture stores, which `test_inv_a8_improve_authority.py:231-247` requires. No run confirms the refusal fires as written. |
| Member/grader task split | **`measured` two ways, against frozen artifacts** | `packet.member_task_view` is an allowlist at the executor. Static replay of all 54 frozen tasks under both control strategies gave 0 of 27 mismatches per family per strategy; 108 real subprocess runs through the real reducer graded `preserved` on 27 of 27 per strategy with 0 leaked fields. Filtering at a call site would have stripped the grader too and measured `invalid` for every candidate. |
| Expressive-action probe (M3) | **`negative`, closes M3** | 33 of 39 SWE tasks admit exactly one repair; **0 of 39** admit two semantically plausible ones. The 8 second repairs disagree with the reference on 81 to 1575 of 2106 swept inputs. Zero dispatch cost, so it runs on every task of every world. |
| SWE scorer | **`over-claimed`, a defect found by the probe** | `tasks.score` decides from two public cases plus one protected case and already credits programs disagreeing with the reference on up to 75 percent of inputs. Any SWE freeze taken now would freeze an over-counting verdict. Fix belongs to `s09_swe_tasks.py`. |
| CI starting state | **`measured`, and it is red** | Two runs. Baseline `37172638343` at `0ee4699`: **259 distinct failing IDs** (245 FAILED, 14 ERROR), 4 of 7 suite matrix entries cancelled, 160 failures unrooted. Run `37236035655` at `7a00676`: **268 distinct IDs across 81 files** (heavy 72, py3.133 113, py3.132 55, py3.131 28, reconciling exactly). **That head is 26 commits behind the tip, so both counts are floors describing trees behind this one.** **No green baseline exists.** The 15 failures in `test_inv_a_action_meaning.py` are pre-existing: their IDs are byte-identical across both runs. |
| Row identity | **`measured` broken, and the outstanding item** | `_live_investigation_id` mints `study_root-run_id-label`; `campaign_id` mints `ad01-w{world}-{arm}-{seq}-{token}`. Nothing carries one to the other, so `mission.is_quiescent` has no production caller. |
| Deliberate reds | **4, expected** | `test_r123_gates.py:192,204,210` and `test_invl02_causality.py:348,1042` drive a round on an owned store. Green at `0ee4699`, red now, because each was measuring the authority defect. The other 38 store-creating call sites across five test files are nameless and unaffected. |

**The limit on disposition 1, corrected by the independent review and recorded
here so it is not lost.** At `8a207ab` the gap was wider than a computed
subscript key: `view.update({"grant": x})`, `|=`, `pop` and `clear` all wrote a
frozen field the guard never inspected. The dynamic before/after comparison in
`admit_revision_under_freeze` was credited as the layer that catches this and
**cannot fire** — a revision's bytes run out of process against a JSON view
carrying none of the six frozen fields, and the store compared is never in the
child's reach. There is no runtime backstop; the static check is the whole of
the freeze. X3 closed this by matching the parse's own binding contexts and
adding the key-taking and keyless method forms, and deleted the helper whose
docstring promised a backstop that could never run.

**What the review also found on the causal side, and what is now repaired.**
`s09_policy_state.effect_id` was minted as the constant
`ad01-<cid>-b<seq>-effect`, which named no `operations` row and was read back by
nothing, so the admitted-effect to observation arrow was durable on both sides
and joined only by `(investigation_id, seq)`. Measured against real
PostgreSQL: 3 of 3 such ids absent from `operations`, and no observation
carrying an operation or effect id — which is structural, because
`attempt_observations` is `(id, attempt_id, content, created_at)` and has
neither column. Of the chain's seven arrows, five were always causally bound.
X4b made the identity a reader: it is read off the episode, then checked
against `operations WHERE settled` before being written, so the database has
the last word and an episode's own string cannot make the column true by being
written to. The honest limit is that a host-side diagnostic boundary admits no
operation at all, and there the row carries an empty identity, which is a true
answer rather than a fallback.

**What the freeze gates, measured rather than assumed.** The repair above is
sound: `tests/test_inv_x3_freeze_methods.py` gives 38 passed. Whether it
matters to the running system is a separate question, and it was answered by
measurement rather than by reading the guard's quality.

`admit_revision_under_freeze` has exactly one non-test caller,
`learner_revision.acquire` (`:572`). That function has no production caller.
`git log -S "learner_revision.acquire"` over `experiments/`, `scripts/` and
`src/` returns nothing, so it never had one either. Production imports of
`learner_revision` reach only `paired` (`e2_replication.py:738,1378,1379`) and
`evidence_ceiling`. `w1_e1_campaign_r2.py:348` lists `learner_revision.acquire`
as a site that acquires a revision and marks it `e1_path: False` in the
project's own words.

The live path is a different function entirely. A model-authored improver
enters at `live_construct.parse_and_build_live_package`, whose only source gate
is `method_exec.verify_step_source`; its one shipped caller is
`scripts/invl02_live.py:1987`. Two measurements decide what that means.

* A `STEP` entry writing all six `FROZEN_FIELDS` by subscript **and** through
  `view.update({"grant": ...})` is **admitted** by `verify_step_source` and
  **refused** by the freeze guard (`writes view['grant'], a frozen field`). The
  same bytes, two gates, opposite verdicts.
* The live `IMPROVE` view carries **none** of the six names.
  `frontier.step_view` (`:1763`) adds `frozen_source`, which holds
  `op_source`/`imp_source`/`op_digest`/`imp_digest` and no frozen field. So
  there is no live write of a frozen field for a guard to catch, and the
  guard's own docstring already says the out-of-process bytes run against
  exactly such a view.

Wiring the guard into the live path would therefore not add protection; it
would subtract admissions. The scope check is not a quality bar a better
reply could clear — it is structural. `unauthorised_change` (`:354`) compares
`_program_shape(incumbent)` to `_program_shape(revision)` with the probed input
blanked, so admission requires the reply to *be* the incumbent modulo one
integer. A free-form model reply is not a derivative of the incumbent at all,
and no prompting fixes that.

Measured through `admit_revision_under_freeze` against the same bound store and
views `tests/test_inv_c2_freeze.py` builds: all four authored controls stay
`eligible`, while a free-form improver of the shape a model reply takes is
refused `changes-an-unauthorised-decision` (it differs from the incumbent in
more than the probe input) and a variant is refused `task-solver-not-decision`.
The scope check exists to police an authored revision inside a fixed channel,
not a free reply outside it. Wiring would refuse the very replies milestone C
exists to acquire.

**So the freeze is correctly dead, and the honest deliverable is to stop
calling it enforced.** It is a real guard over a path the live system left
behind, kept honest by 38 tests. Nothing was wired, because inventing a caller
to make a repair look consequential would be the worse outcome. C4 removed the
construction *menu*; it did not touch the freeze, so this is not a case of
milestone C superseding the guard. The guard was never on the live path to begin
with: `live_construct.py` was added `2026-09-30`, a day before the freeze lane
landed `2026-10-01`, and the two were built without either referring to the
other. The live improver was routed around the channel, not displaced by it.

**The other half, checked so the two are described consistently.** X4b's
`effect_id` repair *is* on a live path: `improve_channel.py:2234` and `:2068`
call `store.admit_and_spend(..., effect_identity={"operation_id":
receipt["operation_id"]})`, reached from `drive_improve_round`, which
`run_live_improve_round` calls. It gates the running system; the freeze does
not.

## 1. Mechanism — confirmed as to the chain, corrected as to the freeze and the causal link

| Requirement | State | Evidence |
|---|---|---|
| Durable dispatch identity across restart | `confirmed` | `tests/test_inv_a_chain.py`, `test_inv_a_counterexamples.py`, `test_inv_a_reviewer_source.py` — 29 passed; seven tamper cases each run a real green baseline in the same test on the same store before the tamper. |
| Authority mandatory, not a runtime branch | `confirmed` | By attribute: `REACHABLE_EVIDENCE`, `MENU_EVIDENCE`, `_STRATEGY_SOURCE`, `_menu_probe` no longer exist on `improve_channel`; `run_step_out_of_process` / `run_member_out_of_process` carry no `dsn is None` branch. |
| Freeze enforced against the parse | **`confirmed` as a guard, and it gates no production path** | At `8a207ab` acceptance probed `improve_channel._attempts_frozen_write` with 19 binding forms it wrote itself and found zero mismatches; all 19 were subscript or attribute spellings, which is why the review's mapping-method forms were missed. X3 replaced the node-type enumeration with the parse's own binding contexts and added the key-taking and keyless method forms (`update`, `setdefault`, `pop`, `popitem`, `clear`, `__delitem__`). `tests/test_inv_x3_freeze_methods.py` refuses every form (38 passed), and a read of a frozen field plus a write to a non-frozen key and to a revision-owned `seen[key]` are still correctly admitted. **What the guard gates is narrower than this row previously implied.** Its only non-test caller is `learner_revision.acquire`, which has no production caller: `git log -S` finds none in the tree's history, and production imports of `learner_revision` use only `paired` and `evidence_ceiling`. The guard is correct and unreachable; see the freeze-wiring note below. |
| One mission owner | `confirmed` | C1 (one durable mission entry) and C6 (one resume owner naming what it resumed); C7 crosses both task structures through it. |
| Control registries agree | `confirmed` | `CONTROL_ROLES` is a strict subset of `WRITTEN_CONTROL_ROLES`. |
| Effect identity bound to a settled operation | `confirmed` after X4b, and **on a live path** | `_s09_effect_id` reads the identity recorded for the boundary rather than computing one, and the derivation checks `operations WHERE settled` before the value is written. `tests/test_inv_x4b_effect_identity.py` (9 passed, measured on WSL Ubuntu against real PostgreSQL) pins that an admitted effect names a settled operation with a receipt, that a fabricated id is refused, that the observation reaches its operation in both directions, and that a boundary admitting no operation carries an empty identity and claims no effect. Unlike the freeze row above, this one gates the running system: `improve_channel.py:2234` and `:2068` reach it from `drive_improve_round`, which `run_live_improve_round` calls. |
| Freeze depth | **`confirmed` as a single layer, and the second layer is gone rather than credited** | There is no runtime backstop: the before/after comparison in `admit_revision_under_freeze` guards admission itself, and the docstring now says only that. The static check is the whole of the freeze, and a computed key is refused as unreadable rather than deferred. A name the guard cannot follow to the view — an alias, a helper argument — remains uncovered; that limit is stated on the function and pinned by a test. |

## 2. Acquisition — negative

| Cell | Result | Evidence |
|---|---|---|
| B12 SWE construction, live | **0 of 4 lineages** | `reports/evidence/invr1b12-swe/campaign.json`: `acquired_lineages` 0, `independent_acquired_lineages` 0, `distinct_acquisition_digests` 0, `no_acquisition_lineages` 4. Every `lineages[i].acquisition_digest` is `null`; every `use_row` reads `outcome: "no-acquisition"`. |
| B12 send reconciliation | **5 = 5 = 5** | `store-rows.json`: five physical sends, five operation ids (`L0-a1`, `L1-a1`, `L2-a1`, `L3-a1`, `L3-a2`), five receipts, one to one. **What the five were is not five attempts at the same thing**: one read timeout settled `unknown`, three HTTP 502 failures, and one success. |
| Retention leg | **0 of 3 over 27 executions** | `reports/evidence/invr1b14-retention/retention.json`: 3 members x 9 rows = 27; one acquisition-task row; 26 comparable; verdict union exactly `{"preserved"}`; `same_reduction_as_seed` true on 26 of 26. |
| Strategy probes | **0 of 4** | All four report `distinct_verdicts: ["preserved"]`. |
| Two other representation cells | **never run** | `typed-ast` and `action-graph` are refused by their own frozen loaders, each with a named witness. No new DSL was built to fill the table. |

**This is a bounded zero resting on one returned artifact, not a rate and not a
proof the route cannot acquire.** Of B12's five sends exactly one artifact was
ever returned. With B17's two further sends the honest denominator is three
prose responses, all `stop_reason: length`, none a policy. The artifact says so
in its own `not_claimed`.

## 3. Utility — negative and not measurable

| Requirement | State | Note |
|---|---|---|
| Compare an acquired method against a control | `not measurable` | There is no learned arm. `acquired_artifacts` is asserted `[]`, `retained_use` is `None`, and no authored substitute appears — the assignment forbids promoting a failed acquisition. |
| Mechanism does not imply utility | `confirmed as a boundary` | Stated explicitly so the disposition-1 result cannot be read across. |

## 4. Transfer — negative

| Leg | Result | Evidence |
|---|---|---|
| Retained reuse vs cold acquisition | **never measured** | Nothing retained was distinguishable from the seed (`preserved` on 26 of 26), so there was nothing to transfer. |
| Two-domain crossing | **transfers a predicate, not answers** | C7. A Boolean probe returns four output bits about a hidden function; the SWE side spends the *distinction* "expected differs from actual, and the result is well formed, so this is a value fault and not an error", applied to its own mismatching public tests. |
| Archive with no usable members | **no-acquisition result** | By the assignment's own rule this is not transfer evidence. |

## 5. Autonomous selection — not established

| Property | Measured | Consequence |
|---|---|---|
| Episode order | 3 Boolean then 3 SWE, fixed in `experiments/ad01/twodomain.py` | A script. Not selection. |
| Crossing power, SWE side | `software-fault-repair-v1` reports **9** clusters, `powered: True` | **This 9 is a union.** `_swe_clusters` (`twodomain.py:119-126`) returns `len(set(DEV_TEMPLATES) \| set(HELD_OUT_TEMPLATES))`, and the two splits hold 3 and 6 templates. Per split that is **3 or 6 against 6 required**: dev is unpowered, held-out is exactly at threshold with zero margin. The union clears the bar through the census the split exists to prevent. |
| Crossing power, Boolean side | `boolean-rule-v1` offers **1** cluster against 6 required, shortfall 5, `powered: False` | The comparison is unavailable from these two instruments. |
| Boolean hypothesis classes | **exactly one** distinct descriptor, identical `class_digest`, `class_size`, `form` and `n_inputs` across 3 splits x 24 seeds | A contrast over it has one independent unit however many tasks it runs. No panel choice can move it. |
| Mission row ownership, **as of `ff5b767`** | **repaired.** `run_two_domain_crossing` takes no dsn, writes no mission row and returns the crossing whole; the five write-only columns are dropped in `migrations/0021` | One of the two named causes is gone. The crossing was the only writer of the projections production did not consume, and it had zero production callers to begin with. |
| Row identity, **as of `ff5b767`** | **broken, and now the blocker.** `_live_investigation_id` (`scripts/invl02_live.py:1899`) and `campaign_id` (`experiments/ad01/trajectory.py:110`) mint different SQL rows | The SQL quiescence predicate has **no production caller** and two quiescence predicates remain. Wiring the SQL predicate into adoption would ask about a row the store's effects were never admitted to; deleting the JSON one would erase a real signal. |

**A two-domain demonstration is not a two-domain result.** The lane does not
claim otherwise and is honest about what its demonstration is.

**Read per split, the crossing is unpowered on both sides.** The Boolean side
offers 1 cluster against 6 required. The SWE side's 9 is the union of two
splits that are 3 and 6 against the same 6. The crossing itself spends 3
Boolean episodes then 3 SWE ones — 2 dev and 1 held-out on the SWE side — so
the arm it actually runs is the 3-unit one. A contrast with one independent
unit per structure is n=1 however many rows it produces, and the design
supplies no way to raise that without new generator families.

## 6. Learner improvement — negative

| Requirement | State | Note |
|---|---|---|
| Live revision attempt | `never run` | `c4-live` has no workstream report, no evidence directory and no test. It is recorded as outstanding in `reports/PLAN.md`, not dropped. |
| Inheritable construction procedure | `confirmed` (mechanism only) | C4 deleted the two-member fixed menu; a descendant now inherits its parent's construction input, so `reachable_evidence` is a function of the program rather than a constant published beside it. `_revision_source(3)`, `(8)`, `(11)` all build ~1067-character sources and all pass the frozen-write check. |
| Revised descendant cohort | **does not exist** | No eligible revision was attempted, so nothing was compared and no learner improved. |
| Per-task policy state in sealed assessment | `never run` | `b5-sealed-state` has no report, no evidence and no test. |
| Runnable on this host, **as of `ff5b767`** | **yes, but this session holds no credential** | A process answers on `127.0.0.1:4000` with `401 invalid api key`, so the route is live. `SETTLEMENT_GATEWAY_ENDPOINT` and `SETTLEMENT_GATEWAY_KEY` are absent from this shell's environment and `config/.env` does not exist. An absent credential is not an absent route, and neither is model incapability. |

Per `WORKER-PROMPT.md`, the prototype's existence does not claim beneficial RSI.
Nothing here claims it.

## 7. Search passes and the defects they fixed

Two passes over the merged tip, each a separate agent from the author of its
target. Both generalisation patterns were verified in source, not read from the
pass reports.

| Pass | Finding | Repair |
|---|---|---|
| P1-01 | A lost hold on `investigations.in_flight` across two connections. | `mission.py` takes `FOR UPDATE`; the read-then-write replace is gone. |
| P2-01 | A **fourth writer** of `in_flight` — the same class as P1-01. | Same barrier, verified at all three call sites. |
| P2-02 | `AnnAssign` / `NamedExpr` reached a frozen write. | `_attempts_frozen_write` now refuses those positions. |
| P2-03 | `take_correction` locked a row the writer might not have created. | `authority.take_correction` inserts the zero row `ON CONFLICT DO NOTHING` **before** the `FOR UPDATE`, making the conflict itself the lock. |
| R-final-01 | `amend_protocol` read a protocol on one connection, committed, and wrote `supersedes` on a second with autocommit, so four concurrent amends of one parent all applied. | X5 holds the parent `FOR UPDATE` and inserts the child in the same transaction, so the read that decided the amendment still holds its lock when the row it decided about is written. The refusal raises rather than returning a `CommandResult`, because `store.transact` converts a raised error into a returned one and two live callers ignore the returned result. |
| R-final-02 | The effect identity was synthesized, so the admitted-effect to observation arrow was bound by position. | X4b reads the identity off the episode and checks it against `operations WHERE settled` before writing. |
| R-final-03 | The freeze admitted a frozen write made through a mapping method, and credited a second layer that cannot fire. | X3 replaced the enumeration with the parse's own binding contexts and deleted the deferral. |

The generalisation the two search passes named — *a lock taken on a row the
writer may not have created yet, or a read and a write split across two
connections* — is the right one, and it produced four real fixes. The
independent review found a fifth in the same shape. All five are repaired.

## 7a. Test migrations, and the red audit

Three lanes migrated tests whose contract a repair had changed, and one red was
not a stale test at all. **MIG-MIGRATE** cleared seven reds that were mostly
stale tests, but two predated the commit they were blamed for: they passed the
literal strings `"assessment-store"` and `"unused"` as a dsn, which `c3181d9`
made fatal. Migrating them made panel cells execute instead of being refused,
which changed the cost — the production revision spends **8, not the pinned
16**, and the old figure was one the panel never actually spent. The migration
count is now read from the same glob `apply_migrations` reads, so the next
migration does not re-break it. **SIB-FIX** cleared four tests off the deleted
two-member menu. One cause was not the deleted symbol: `lineage_descendant_score`
now substitutes the probed input, so the archived artifact names best probe 0
where a live run of the identical call names 7. **That drift predates this
batch and is irreducible, because `reports/evidence/` is immutable**; the test
now pins what is checkable and fails if the menu ever returns. **C14-FIX**
repaired the self-blind gate described below.

**The red audit returned NO: the deliberate reds were not the only reds.** At
the review merge the 51-file affected set carried 16 reds in four classes — 4
deliberate, 3 pre-existing and understood, and **9 unexplained across four
files**, which no document recorded. The worst was
`test_c14_live_already_spent_source.py`, a gate that could not see its own
defect: it excluded any path containing `.worktrees` while deriving `ROOT` from
`__file__`, so inside a lane worktree the scan returned `[]` and compared empty
to empty — green and blind — while in the main checkout it was red for the wrong
reason, listing each sibling lane's copy as a separate hit. **Neither reading
was a statement about readers.** Now repaired and merged. The audit refused to
paper over its own gap: `tests/test_s09_swe_experiment.py` has **no verdict**,
running 7 of its 57 tests before being stopped, and the remaining 50 are
unmeasured.

**Two reds are left standing on purpose.** FA-04
(`test_the_archived_e4_generator_cannot_run_against_the_deleted_menu`) asserts
`hasattr(channel, "REACHABLE_EVIDENCE")`; the *correct* deletion of the fixed
menu falsifies it, and it can only be greened by restoring the deleted menu,
which would undo milestone C's boundary. FA-02
(`test_the_b4_freeze_artifact_its_own_gate_reads_is_committed`) names
`reports/evidence/invr1b4-mean-score/b4-crossover-mean.json`, **which was never
committed** — verified absent from this tree. The one `control_competence(40)`
sweep was cancelled for resource reasons, and the artifact must not be
fabricated to satisfy a gate that reads it. Neither is open work.

## 8. Live campaigns, priced

All figures recomputed from the evidence directories.

| Study | Sends used | Authorised | Unspent | Result |
|---|---:|---:|---:|---|
| B11 served output budget | **6** | 6 | 0 | Served 16, 64, 256, 1024, **2048** with `stop_reason: length` at every rung; **4096 lost** to a read timeout, settled `lost-response` with an unknown outcome. |
| B12 SWE construction | **5** | 25 | **19** | 0 of 4 acquired. One text response, 5783 characters, refused `unparseable-python`. |
| B14 retention | **0** | 0 | — | `measured_live: false`; closed behind a gate that is open. |

**The binding constraint this section previously named was falsified.** It read:
the route serves 2048 output tokens, the authored control policy is 22734
characters, the loader accepts at most 7000, so no response at the frozen budget
could have carried the authored policy. The observation beneath that — 3 of 3
responses were prose, all `stop_reason: length` — is true. The conclusion was
not, and B17 measured it four ways (`reports/evidence/invr1b17-budgetfit/`):

| claim | measurement |
|---|---|
| 7000 is the loader's acceptance limit | it is a constant in B12's driver (`invr1b12_swe_construction.py:192`). `verify_step_source` has no length rule at all and admits the authored control's 22734 bytes and a 115-byte policy. |
| no response at the budget could carry a working policy | a policy that repairs **3 of 9** dev instances is 5551 characters and fits the served 2048-token budget with room to spare. |
| the budget is the binding constraint | falsified. The cause is prose-not-code. |

**The corrected reading.** The budget did cut all three responses, and the cut
is real. But they were prose from their first byte, so no continuation of them
was ever going to become a policy. The truncation is the reason the cause was
never observed to end, not the cause. With B17's two further sends the honest
figure is **3 of 3 responses, all `stop_reason: length`, none a policy** — and
the acquisition denominator is one returned artifact, not a rate. A conflict
inside the evidence file is recorded rather than resolved:
`offline_measurements.compact_repairing_policy.characters` reads 5551 while a
prose sentence in the same record says 5725. The field is the measured one;
both clear both limits, so no disposition turns on it.

Unknown stayed unknown throughout: `billed` and `charge_units` are null on every
receipt from this route, the lost send records `input_tokens: "unknown"` rather
than zero, and no `"billed": 0` appears anywhere. Carried-in historical exposure
(`>= 5563` units) is accounted separately and was never netted against the fresh
allocation.

## 9. Panel power — the FA-01 correction

**Three panels are powered, not one.** Recomputed from
`reports/evidence/invr1b8-panel-census/census.json` across all 14 panels:

| panel | clusters | required | powered | ceiling |
|---|---:|---:|---|---:|
| `graph:dev+transfer` | 6 | 6 | **yes** | 0.285714 |
| `graph:within+transfer` | 6 | 6 | **yes** | 0.285714 |
| `graph:dev+within+transfer` | 6 | 6 | **yes** | 0.285714 |

`graph:dev+transfer` is the **smallest** of the three, which is why B13 and B14
name it. **Smallest is not only.** The seven `software` rows are unpowered, and
`software_templates_in_frozen_world: 4` against `required_clusters: 6` means no
split choice could have saved the archived runs. This is a power defect, and a
panel choice repairs it; it is not the retention closure, which no panel moves.

`minimum_clusters_for_alpha(0.05)` = 6, matching the protocol's `_required_clusters()`.

## 10. Stage 9 keep / change / remove

Under the protocols this batch actually completed. A negative disposition is an
absence of evidence, and removing a mechanism for failing to produce evidence in
one campaign would be reading a null as a verdict.

| Decision | Mechanism | Why |
|---|---|---|
| **Keep** | Durable dispatch identity | Held under tamper; survived two search passes aimed at exactly this seam. |
| **Keep** | Authority as a mandatory type | `dsn is None` is no longer a branch. A2 closed the hole and A6 migrated all five callers with no carve-out. |
| **Keep** | The freeze guard and its refusal suite | A guard and its refusal suite cannot both pass by the guard being broad: X2 widened it by enumeration and the authorised revision stayed eligible, and X3 then replaced the enumeration with the parse's own binding contexts. **Keep the guard and the suite; do not read the row as a claim about the running system.** The guard gates `learner_revision.acquire`, which no production code calls. |
| **Keep** | One mission owner with suspend/resume | C1 retired the partial owners; C6 gave resume a single owner. |
| **Change** | Construction menu | C4 replaced the fixed two-member menu with an inheritable construction procedure. |
| **Change** | Capability naming | B3 opened the repertoire, so a `seed-`-prefixed family convention is no longer the only admissible id. |
| **Remove** | Nothing | No disposition in this batch licenses a removal. |

## 11. Stage 10

C7 landed the connected mission prototype: one persistent mission entry with
frontier, permitted experience, active program, acquired artifacts, retained use
and improvement mode, demonstrated across both selected task structures.

**Its existence does not claim beneficial RSI.** No eligible revision ran, so no
learner improved and nothing here supports such a claim. It is prototype level,
not the connected general prototype Stage 10's own definition requires, and it
is not qualified for deployment.

**Corrected by the 2026-10-04 batch.** Five of the six fields this paragraph
names were the write-only columns, and they no longer exist. The persistent
entry carries the charter and `improvement_mode`; `in_flight` is the only other
mission column, and it has real readers. The sentence above is retained as what
C7 landed, and this paragraph is what remains of it. The prototype is further
from stage 10 than that sentence implies: M2 is not started and its central
clause is undemonstrable as written, the two investigation rows are not the same
row, and M4 is unstarted work rather than blocked work.

## 12. Outstanding

Rows marked 2026-10-04 are new in that batch. Nothing below was softened; the
rows the batch did not touch keep their prior state and wording.

| Item | State | Why it is not closed |
|---|---|---|
| **Row identity (2026-10-04)** | **blocking** | `_live_investigation_id` and `campaign_id` mint different SQL rows and nothing carries one to the other. Upstream of M2 and of the quiescence repair. |
| **Mission round-result writer (2026-10-04)** | **outstanding** | `improve_channel.py` still appends to `store._doc["round_results"]` directly. The entry now asks the store's validator before the save, so a document the store would refuse to reopen can no longer be written. That is not the repair; the repair is a `FrontierStore.record_round_result` method or moving the projection to SQL. |
| **S09 scorer equivalence check (2026-10-04)** | **repaired, and any freeze on the old counts is void** | `cb7012c` decides equivalence structurally instead of over a sampled box: `bb40300`'s 1815-case sweep was defeated by a gate reading only public module constants. **The normal form is not alpha-equivalent, so a behaviourally identical rename is refused.** A repair rate read off this instrument is a lower bound on repairs and never an upper bound on wrong ones, so any SWE freeze taken before it is over-counting and must be re-taken. |
| **Green CI baseline (2026-10-04)** | **does not exist** | 259 distinct failing IDs at `0ee4699`, 4 of 7 suite matrix entries cancelled, 160 unrooted. Counts are a floor and describe a tree behind the tip. A lane cannot separate its own regression from pre-existing red without re-measuring. |
| **Four deliberate reds (2026-10-04)** | **expected red** | `test_r123_gates.py:192,204,210` and `test_invl02_causality.py:348,1042` drive a round on an owned store and now hit the refusal. Each was measuring the defect. Restoring them means supplying real authority from `live_construct.py` and `invl02_live.py`. |
| M3 supported cells | **`negative`, closes the study** | 0 of 39 SWE tasks admit two semantically plausible repairs; AD01 fails on four independent grounds; Boolean and ordering cannot execute a program. The supported-cell count is zero, measured. Repairing the SWE scorer does not change that, because the alternative repairs are overfitted to three cases rather than correct. A **valid** null: M3's own question is answered, and stages 9 and 10 are not thereby closed. |
| `c4-live` | **never run** | The milestone-C deliverable. The mechanism that would make it runnable exists and is eligible; nothing was attempted against it. The route is live on this host. |
| `b5-sealed-state` | **never run** | Per-task policy state in sealed assessment, asked for in `WORKER-PROMPT.md` §B. |
| B4 crossover | **unmeasured** | The single `control_competence(40)` sweep was cancelled for resource reasons before it returned. A cancelled measurement is not a null measurement: nothing about the crossover is known in either direction. |
| Acquisition | **open** | 0 of 4, on one returned artifact. The output budget is **not** the binding constraint; B17 falsified that and the remaining live question is a route-and-protocol one, since 3 of 3 responses were prose where the protocol asked for code. |
| Two-domain comparison | **not askable** | One independent unit per structure: the Boolean side offers 1 hypothesis class against 6 required, and the SWE side reaches its threshold only by counting dev and held-out together (3 and 6 per split). The order is also a fixed script. Both need new instrument families, not a new panel choice. |
| Effect identity unbound to a store row | **repaired** | X4b closed it. Recorded here because the *shape* is the lesson: the chain's proof was the existence of rows, and the causal binding was tested by nothing, so it would have kept proving the weaker thing after every other defect was fixed. |
| `tests/test_s09_swe_experiment.py` | **unmeasured** | 7 of 57 tests completed; the remaining 50 have no verdict. Three attempts were stopped by their own timeouts, the last by the coordinator. A batch that cannot finish is a finding about the host, reported here as a gap rather than as a pass. |

## 13. Documentary defects recorded, not repaired in place

| Finding | Disposition |
|---|---|
| `reports/evidence/inv_r1_e4/make_evidence.py:238` reads `channel.REACHABLE_EVIDENCE`, deleted by C4. | **Recorded, not fixed.** Archived evidence. Its outputs remain valid history. |
| `reports/evidence/inv_r1_e2_offline/make_evidence.py:242` mints only `seed-%s-%s` ids, the convention B3 opened. | **Recorded, not fixed.** Not a dangling reader — it still runs — but its output describes a world where a `seed-` prefix was the only admissible id. |
| `experiments/ad01/twodomain.py:102` and `tests/test_inv_c7_two_domain.py:16` say the Boolean instrument "publishes 120 tasks"; the census iterates 3 x 24 = **72**. | **Recorded, not fixed.** One propagated figure across two agreeing files. It changes no measured claim: the cluster count is 1 across 72 and would be 1 across 120, because every task comes from one class. Left to the owning lanes. |

No file under `reports/evidence/` was edited. The two archived generators are
recorded here and in [`FINAL-ACCEPTANCE.md`](FINAL-ACCEPTANCE.md) rather than
annotated in place, because adding a file to an archived evidence tree is the
first step toward editing one. The two deliberately-red findings in §7a belong
to the same rule and are recorded for the same reason: neither can be repaired
without either editing an immutable evidence tree or restoring a boundary that
was correctly deleted.

## 14. Independent acceptance

`reports/FINAL-ACCEPTANCE.md` is the acceptance pass's own report, at `8a207ab`
over `794737f`, base `70223fb`. Its four recomputed numbers — panel power, the
retention leg, B12's send reconciliation, and the Boolean hypothesis class — all
agree with this matrix. **The numeric layer is sound.** What the pass's own
verdict did not reach is what an independent review then found, and what this
file now records above: the freeze was over-claimed and the effect identity was
causally unbound, both named in the documentary layer's favour. The defects the
acceptance pass found were in the documentary layer and in the freeze, which the
review then measured directly rather than leaving unmeasured.

One correction survives all of that, and it is about coverage rather than
quality. The freeze repair is a correct guard over a path nothing calls; the
effect-identity repair is a correct guard on the path the running system
actually takes. Reading "both halves repaired" as "both halves gate the system"
is the same category of error the review overturned at `8a207ab`, one level up,
and this file now says so in the disposition, the mechanism row, the Keep row
and the freeze-wiring note rather than leaving a reader to infer it.
