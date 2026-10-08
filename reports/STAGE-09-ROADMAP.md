# Stage 9 roadmap: completion matrix, decision table, and the next conceptual decisions

Historical study assessment, superseded as an active plan on 2026-10-08.
Use [the refinement roadmap](../docs/design/REFINEMENT-ROADMAP.md) and
[the project ledger](PROJECT-LEDGER.md) for current architecture and work.

Against `693575e` on `codex/implementation-investigation-learning-02`. The requirement is
`WORKER-STAGE-09-PARALLEL-EXPANSION.md` line 115 (completion matrix, decision table, six-way
separation, ranked decisions) and line 117 ("The researcher then uses the combined results to
decide the next architecture revision").

**What this file is not.** It does not pick the next architecture. The handoff forbids silently
choosing one to manufacture progress, and this branch has already retracted nine of its own
claims today. Ranking the *decisions* is what the handoff asks for; choosing among the options
inside a decision is the researcher's, and this file says so at every rank.

**How to read the evidence labels.** Every result below carries one:

| label | meaning |
|---|---|
| `ARTEFACT` | read directly from a machine-readable file in `reports/evidence/`, cited by name |
| `PROSE` | read from a lane's `RESULT.md` and not independently re-derived |
| `UNVERIFIED` | inherited from a report and flagged as not re-checked by its own author |

Where a source disagrees with the branch's running summary, the source wins and the
disagreement is named. Five such disagreements were found while writing this file; they are in
section 7.

---

## 1. The six-way separation

The handoff names six things and says to separate them. The separation exists because a result in
one bucket reads as a result in another if the reader is not forced to keep them apart. Nine
retractions on this branch came from exactly that: a harness property reported as a capability, a
prior reported as an effect, an estimator artifact reported as a substrate property.

Each bucket below states three things. What was learned. What was **not** learned, named
specifically. And what supports it.

### 1.1 Mechanisms

**Definition.** Does a proposed mechanism hold, independent of any model's behaviour and
independent of whether the thing it measures ever runs? This is the bucket that produces
engineering findings, and on this branch it is the only bucket that produced a clean result.

**Learned.**
- The instrumentation is sound enough to make a null interpretable. `channel_headroom`'s
  qualification holds over 24 seeds: a known-effect revision moves descendants +0.2596, a no-op
  moves them **exactly** 0.0, and a disconnect moves them **exactly** 0.0 against a descendant
  that learned nothing. `ARTEFACT` (`reports/evidence/inv_r1_e4/headroom.json`, key
  `qualification`).
- The sever control is a valid control. 24 cells, 2 policies x 3 worlds x 4 budgets; the severed
  arm is a strict prefix of the connected arm in every cell; 18 cells had an effect to lose; the
  effect vanished in all 24. `ARTEFACT` (`e3-sever-control.json`, keys `cells_total`,
  `cells_with_an_effect`, `effect_vanished_in_every_cell`, `severed_is_prefix_in_every_cell`).
- The launcher is explicitly not containment. `src/settlement/launcher_local.py:12` says so in its
  own docstring, and N-36 recovered an invertible task seed in 959 ms through a real launcher.
  `PROSE` (N-36's own row, which marks the recovery as NOT re-run).
- The measurement environment is itself a finding. 1045 `could not serialize access` and deadlock
  events in twenty minutes on hardcoded shared database names, peaking at 124 in one minute. No
  green suite in this environment has established store-path behaviour for the hardcoded files.
  `UNVERIFIED` (N-46, which marks the postgresql log as not re-read).

**Not learned.**
- Whether the "evidence" the study collects survives an adversary who reads the repository. N-36
  is open at critical. Every acquisition claim in this batch is unsafe under that threat model
  and no measurement in this batch tests it.
- Whether any engineer's judgement in the ledger is right. N-53 records Jev as unavailable, and
  an independent audit found no persisted Jev artifact for E1, E3 or E4.
- Whether the three denominational repairs (CS-01, N-02, N-03) hold under a live send. N-31 is
  split-verdict: two sources of truth confirmed present, live under-count unconfirmed.

**Why the separation matters here.** The `channel_headroom` figure of -0.0222 is the textbook
case. It sat in this bucket where it read as a fact about the substrate. It is a property of the
estimator (N-63: full-cohort spread against half-cohort noise floor, so `headroom < 0` by
construction). Three report claims were corrected because of it. Had it been filed under
"improver benefit" it would have read as an experimental result and been cited for a month.

### 1.2 Acquisition

**Definition.** Can a model produce executable bytes for this task, from this prompt, in this
representation?

**Learned.**
- One live acquisition executed on three real software tasks. M3 run 8
  (`reports/evidence/inv_r1_m3b/use_records.json`) records 36 use records: 3 executed, 33
  refused. The 3 executed `acquired-sw-5b65c917` at normalized reductions 0.769, 0.700 and 0.300,
  the third on a transfer task, each through a real admitted operation. `ARTEFACT`.
- Acquisition yield is low but the refusals are not boundary defects. 30 of 33 refusals read
  "use ran with no policy: the method identity must come from an admitted policy action" and 3
  read "admitted 'acquired-sw-5b65c917' is scoped to 'software' and cannot answer a graph task".
  That is empty repertoires and scope, not a broken contract. `ARTEFACT`.
- **The one acquired member chose the signature default.** Its `executed_source` is
  `reduce_software(task, oracle, method="ddmin", ...)`, the same call `seed-sw-ddmin` resolves to.
  The method default has since been removed from the reducer signature, which is what made the
  menu observable at all. `ARTEFACT` + `PROSE` (`reports/evidence/inv_r1_e1_comparison/RESULT.md`).
- On the SWE panel, the STEP representation repairs most instances whose reference repair is
  inside its candidate space, and misses ten that are not. After the ceilings were derived,
  `probe_reach` is 30/30 held-out and 9/9 dev. `PROSE`
  (`reports/evidence/inv_r1_e1_swe_ceiling/RESULT.md`, section 4 and 5).

**Not learned.**
- **The single most important gap.** The ceiling lane's `RESULT.md` cites
  `matrix.json` in its own directory for "the exact per-family counts" (lines 21, 216, 342, 355).
  **That file does not exist**, and `git log --diff-filter=A` confirms it was never committed. The
  commit `61593be` added only `RESULT.md` to `reports/evidence/inv_r1_e1_swe_ceiling/`. The
  after-picture's repair *rate* is therefore a prose claim with no machine-readable backing at
  this tip, and section 7 of that same `RESULT.md` says so itself in a different voice ("The
  negative is the result").
- Two of three representations have no SWE cell at all. `typed-ast` (8 cells) and `action-graph`
  (8 cells) are recorded as missing with reasons, and the reasons are **not** budget-shaped: the
  frozen validator has no `use` action and `_VIEW_TYPES` exposes no field carrying the program,
  and no SWE `World` value exists. `ARTEFACT` (`e3`… sorry, `inv_r1_e1_swe/matrix.json`, key
  `missing_cells`).
- The SWE comparison is not a comparison. The common harness requires exactly eight public-state
  fields and the SWE world publishes twelve; `admit_world_view` returns
  `non-contract-action-kind` for every SWE view. SWE numbers are comparable within their own
  driver and **not** with the boolean or ordering worlds. `ARTEFACT` (`matrix.json`, key
  `path_fork`; and the module docstring at `experiments/ad01/s09_arm_parity.py:39-48`).
- Whether the SWE repairs are acquired or authored. The single repaired lineage in M3 was
  `python-step` on 4 lineages (`lineages_per_cell: 4`), and the ceiling run is on the world's own
  driver. No acquired SWE policy has been scored against an authored control on the same
  instances.

**Why the separation matters here.** The retracted SWE zero was three separate defects presenting
as one clean zero, and each time the zero looked like a result (N-57, N-59, N-60). A reader who
sees "acquisition: 0 of 24 families" has been told about the *instrument*, not the *model*.

### 1.3 Utility

**Definition.** Given bytes that exist, do they do anything on a task, at what cost?

**Learned.**
- Utility exists and is measurable on the boolean and ordering worlds. All three representations
  are `comparable` and agree. On boolean, `dev/11/8` scores 0.0625 for step and 0.0625 for ast
  with one query spent. `ARTEFACT` (`reports/evidence/inv_r1_e1_matrix/matrix.json`).
- Utility exists on the software world through an acquired member, at three named reductions.
  `ARTEFACT` (`inv_r1_m3b/use_records.json`).
- **An acquired method choice is not better than an authored one.** The E1 side comparison scored
  acquired `greedy` against authored `ddmin` on three use tasks: 23 total operations against 23.
  Different bytes, different per-task outcomes, identical total. `PROSE`
  (`reports/evidence/inv_r1_e1_comparison/RESULT.md`).

**Not learned.**
- Everything on the ordering world is a zero. All five tasks, all three representations, 0.0, in
  exact agreement. The typed AST's frozen node set has no symbolic `lt`; the graph and STEP
  commit a written-down order rather than deriving one. This is a parity result and a ceiling
  result at once. `PROSE` (`reports/evidence/inv_r1_e1_ordering_matrix/RESULT.md`).
- Three tasks is a sample. The `greedy` against `ddmin` tie is not an effect size and supports no
  claim that `greedy` is worse or better.
- Whether the acquired member's utility would survive if the method default were still present.
  The single executed member chose `ddmin`, so its reductions may be the authored baseline's
  reductions wearing acquired bytes.

**Why the separation matters here.** "Utility exists" and "utility came from the model" are
different claims. On this branch the acquired member's method is the authored one, and the
`greedy`/`ddmin` tie is the only place the two were separated, and it came out even.

### 1.4 Transfer

**Definition.** Does retained or transferred behaviour help on new families or domains once its
acquisition cost is included?

**Learned.**
- **Retention is a cost mechanism with a computable crossover.** Retained arm 16345 units for 5
  uses, cold arm 19614. Per-use 3269.0 against 3922.8. Crossover at 5 uses. This is arithmetic over
  the cap sheet's `unit_allowance.per_request` and **no model behaviour is involved**, which is
  why it is the one E2 result that cannot be retracted by a better dependent variable. `ARTEFACT`
  (`reports/evidence/inv_r1_e2_retention/costs.json`).
- The crossover moves. It is `construction_price / use_price`, so it must be recomputed per
  campaign and never carried as a constant.
- One transfer task executed through an acquired member at 0.300 reduction. That is a single
  instance and it is the weakest of the three executed records. `ARTEFACT`.

**Not learned.**
- Source-to-target adaptation is a **tie**, not a benefit and not a harm. Adapted and target-only
  arms both score 1.0, both `evidence: 0.0`, both select `seed-gr-ddmin`. One task, one dispatch
  per arm. `ARTEFACT` (`inv_r1_e2_scored/remaining-contrasts.json`, key `transfer`).
- Whether adaptation ever *helps* is entirely unaddressed. The tie is a null on a sample of one.
- The 2294 uncertain units from r4 and the older 3269 are unsettled exposure, not transfer
  evidence, and the ledger carries them at line 562.

**Why the separation matters here.** A cost crossover is a transfer *mechanism* result, not a
transfer *effect* result. The handoff asked "does retained behaviour help on new task families",
and the honest answer has two halves in different buckets: retention pays for itself after five
uses, and nothing has shown that a retained policy *behaves* better on a new family than a cold
one.

### 1.5 Autonomous selection

**Definition.** Can the system choose which investigation to run, rather than following an
authored sequence?

**Learned.**
- The treatment is **active**. The sever control establishes this on executed evidence for the
  first time in this branch: severing the decision consumer produces a strict prefix in all 24
  cells, 18 of which had an effect, and the effect vanishes in all 24. `ARTEFACT`.
- Both policies demonstrably choose differently from the same portfolio at budget 14 on world 0:
  the agenda picks `seed-sw-ddmin` then `seed-sw-greedy`; the control picks `seed-gr-ddmin` then
  `seed-sw-ddmin`. `picks_differ: true`. `ARTEFACT` (`e3-divergence.json`).
- E3's decisions now reach real admitted operations, written by the E3 path itself. A run at
  budget 40 on world 0 wrote **5** operations, all 5 in the store, 5 receipts, 5 admitted
  decisions; the severed arm wrote 0 and admitted 0. `ARTEFACT`
  (`reports/evidence/inv_r1_e3_selection/e3-admitted-operations.json`).
- **Wiring the store changed no number.** The `science_unchanged` block records a measure digest
  of `ce5a140aff83bccc55a916958fdbaf568cb7c576d5c6a66361510181c83cf7e8` and states every frozen
  measure at every budget is byte-identical to the pre-fix run at `52235a6`. `ARTEFACT`.

**Not learned.**
- **The committed ladder is pre-fix, and the fix it is credited with was never applied.**
  `e3-crossover.json` was last written at `02ce64b` (01:28). This line previously read that
  the `crossover()` sharing fix landed at `52235a6` (07:57). **It did not.** `52235a6` fixed
  `sever_control()`, which builds a fresh policy per cell
  (`s09_e3_selection.py:294-299`); `crossover()`'s body is byte-identical across `02ce64b`,
  `52235a6`, `254f43e` and HEAD, and running it at HEAD reproduces the committed artifact byte
  for byte (sha256 `40dba4d6de15e16a`). The artifact therefore describes one stateful instance
  walking all three worlds and all six budgets, which is what
  `reports/STAGE-09-CONNECTED-STATUS.md` line 174 retracted. **The branch's running
  summary says N-51 fixed this and that "E3 writes real admitted operations". That is true of the
  store path and false of the ladder.** The store path is fixed; the ladder is not, and the
  defect is still live in the code — the artifact is current, not stale. The post-fix ladder,
  built as a separate path rather than a regeneration, is at
  `reports/evidence/inv_r1_e3_ladder/`; 42 of 48 measures move under it. See ledger N-413.
- **The post-fix sever control contradicts the retracted explanation.** The sever control builds
  a fresh policy per cell (`severed_is_prefix_in_every_cell: true` depends on it), and aggregating
  it over three worlds gives, at budget 60: agenda 15 retained / 15 correct / 0.2059 held-out,
  control 8 retained / 11 correct / **0.3910 held-out**. At budget 40: agenda 9 / 9 / 0.1447,
  control 5 / 8 / **0.3593**. The retracted story was that the control is a six-wide schedule that
  spends out at budget 20 and stops while the envelope is unspent. In the fresh-policy data the
  control's held-out advantage *grows* from 0.0000 at 14 and 20 to 0.359 at 40 and 0.391 at 60.
  That is the opposite shape, and it is the shape of a policy that was previously starved rather
  than one that is now saturated. The saturation explanation was an artifact; the truth is not yet
  measured.
- The E3 held-out measure is not a clean read. `e3-divergence.json` records
  `held_out_reduction: 0.08465608465608465` for the agenda at budget 14, while the sever control
  records `0.0847` for the same policy, world and budget. Two artifacts of the same measurement
  disagree in the fourth decimal place.
- This measures bounded autonomous investigation management. It does not establish open-ended
  scientific discovery (handoff line 75).

**Why the separation matters here.** E3's sever control and E3's store wiring are both
*mechanism* results, and both are correct. Neither is a *benefit* result. The temptation the
handoff's sentence exists to block is exactly this: a valid control plus an active treatment plus
real admitted operations, read together as "autonomous selection works".

### 1.6 Improver benefit

**Definition.** Can the system acquire an executable revision of its own learning procedure that
causally improves a later acquisition cohort?

**Learned.**
- **Nothing was learned about improver benefit, and that is the result.** No live campaign was
  run, and the decision not to run one is correct: it would have spent budget measuring noise.
- The intervention boundary is real and named: `imp_source` picks a probe input,
  `drive_improve_round` spends it, and the output bit selects the descendant package. Two tests
  drive real rounds and confirm different probe inputs build descendants with different digests.
- The apparatus is qualified over 24 seeds: known-effect +0.2596, no-op exactly 0.0, disconnect
  exactly 0.0. A qualified apparatus returning a negative is the handoff's own standard for a
  completed experiment (line 117: "An honest negative can complete an experiment"). `ARTEFACT`.

**Not learned.**
- The ceiling is 0.00267 over **every input the instrument accepts**, with all sixteen input means
  between 0.0588 and 0.0609. The reachable descendant set is {3, 11}; the paired difference is
  -0.00138 with a standard error of 0.00123, z = -1.12 at N=1500, and 4619 seeds would be needed
  to resolve it at 95%. `ARTEFACT` (`headroom.json`, keys `ceiling` and `population`).
- **"The substrate has no headroom" and "my probe cannot reach the headroom" are different
  conclusions with the same number attached.** The ceiling measurement is over the instrument's
  own input menu, and the instrument is frozen. A decision that *changes the descendant scoring*
  would not be visible to this measurement at all. N-63's own recheck records
  `best_beats_incumbent: true` (0.0667 against 0.0222), which is the opposite of the claim this
  branch reported for twenty hours. `ARTEFACT` (`headroom.json`, key `headroom`).
- N-26 is still open and latent: an admitted revision can have selected nothing and still report
  `informs_decision: True`. It must be fixed before any future E4 run can trust the field.
- `channel_headroom` has a test that pins its own defective number. `tests/test_s09_e4_channel.py`
  lines 14-17 pin -0.0222, 0.0667 and `measurable: false`, and
  `tests/test_s09_e4_evidence.py:69` asserts the artifact equals a live run. A substrate change
  will surface as a failure; so will an estimator change. This is worth naming: the test suite
  currently protects the defect as carefully as it protects the mechanism.

**Why the separation matters here.** This is the bucket where the handoff's guard bites hardest.
The apparatus is qualified, the decision is real, the estimator was broken, and the substrate
answer is negative. Every one of those is true. None of them is an improver benefit, and the
previous draft of this branch's status report said "the channel has no headroom" in a sentence
that a reader would reasonably quote as an empirical finding about the world.

---

## 2. Expanded completion matrix

### 2.1 Original milestones M0-M4

| Milestone | State | Evidence | What is left |
|---|---|---|---|
| M0 inventory and map | **done** | `reports/PLAN-STAGE-09-CONNECTED.md`; all three findings reproduced at the source | nothing |
| M1 budget and authority | **done for the study, with a critical defect in the shared settlement path** | three separate currencies: `Charge.budget_units` returns `None` unless the charge was reported (`experiments/ad01/s09_route_cost.py:95-102`), and `study_ceiling()` in `s09_study_preflight.py:1230` is documented as three currencies with one subtraction | N-29 closed as a consequence of N-30. N-30's guard is at `src/settlement/store.py:1678`: a receipt is admitted on `prior and not (resolves_unknown or additional_observation)`, and `additional_observation` is the branch coord02 depends on. N-32 remains open and reachable: a declared ceiling whose name is not in `CEILING_COUNTERS` hits `if counter is None:` at `store.py:1196` and `continue`s at `:1202`, so it is stored as authoritative and never checked. |
| M2 representations and worlds | **partial, and the status table's "partial" is right** | three registrations in `s09_arm_parity.REAL_REPRESENTATION_KINDS`; `episode_runner` raises for an unknown name | the SWE world is registered but the harness cannot normalise its view (`common_path_usable: false`). Two of three representations have no SWE cell. The AST node set has no symbolic `lt`. |
| M3 prospective live pilot | **run twice; run 8 supersedes run 7; the result is execution, not derivation** | `reports/evidence/inv_r1_m3b/`: 30 model calls, 564 witness queries, 3 executed use records, 33 refused | the acquired member's `method_source` is the authored `ddmin` call, so it reproduced the authored control. The default is now removed, so the menu is observable and the run has not been repeated. |
| M4 independent verification | **all three options measured; none is a working option; the claim choice is the researcher's** | `reports/evidence/inv_r1_m4_baseline/`, `inv_r1_m4_design/OPTION-THREE.md` | M4's real blocker is that the free-route model will not answer in the admitted format, so there is no clean baseline and therefore no tamper test. This is a *different* problem from the verifier self-hash, which is closed. |

### 2.2 Experiment cells E1-E4

| Experiment | Planned cells | Run | Missing / void | Reason for each gap |
|---|---|---|---|---|
| E1, boolean matrix | 3 representations x 5 tasks | **all 15 comparable**, agreeing | none | — |
| E1, ordering matrix | 3 x 5 | **all 15 comparable**, agreeing, all at 0.0 | none missing; the whole world is a ceiling | frozen AST node set has no symbolic `lt`; all three commit a written-down order |
| E1, SWE | 3 representations x 24 families x 4 lineages | `python-step` only, 156 instances / 468 rows; before-picture **retracted** at `ff27740` | `typed-ast` 8 cells, `action-graph` 8 cells | `typed-ast`: frozen validator has no `use` action and `_VIEW_TYPES` has no program field. `action-graph`: no SWE `World` value; a SWE observation names none of the admitted paths. **Neither is budget-shaped**, and neither changed when the budget rose. |
| E2, relevant vs none | 1 contrast | run, **retracted** | — | dead observable; the `diagnostic` field agreed between arms in every condition |
| E2, relevant vs irrelevant | 1 contrast | run, **retracted** | — | same observable |
| E2, retained vs cold | 1 contrast | **survives** | — | cost result; no model behaviour |
| E2, source-to-target adaptation | 1 contrast | **void, then re-run to a tie** | — | the arm never left the echo on the first attempt; on the scored observable both arms select `seed-gr-ddmin` |
| E2, observation substitution | 1 contrast | **survives, as an envelope result** | — | 3 construction/language defects in the acquired bytes, not a family-preference result |
| E2, replication | 2 independent campaign namespaces | **not run** | 1 of 2 namespaces | the handoff's line 67 requires it for a replication claim. No replication is claimed, so nothing is outstanding beyond the claim that cannot currently be made. |
| E3, selection ladder | 2 policies x 3 worlds x 6 budgets | **run, but pre-fix** | budget 8 and 30 rows are pre-fix only | `e3-crossover.json` predates the `crossover()` sharing fix. |
| E3, sever control | 2 x 3 x 4 = 24 cells | **run, post-fix** | none | 18 cells had an effect; it vanished in all 24 |
| E3, store witness | 1 | **run, post-fix** | none | 5 operations written by the run itself |
| E4, apparatus qualification | 3 controls over 24 seeds | **run** | none | known-effect +0.2596, no-op 0.0, disconnect 0.0 |
| E4, headroom | 1 channel | **run, post-hoc estimator** | live campaign deliberately not run | the ceiling over all sixteen inputs is 0.00267 |
| E4, live campaign | 1 | **not run** | 1 | would have spent budget measuring noise |

Line numbers in this file were checked against the working tree at `693575e`. The ledger's
citations for N-30 and N-32 are stale by roughly fifty lines (it says `store.py:1632` and
`1150-1156`; the code is at `1678` and `1196`/`1202`), which is the same class of error the
ledger itself flags in its last section. Where I cite a line here I have read it.

### 2.3 Unavailable treatments and unrun cells, with the external reason for each

This is a list, not a hedge.

1. **Jev, at every call from `74261ef` onward.** `403 RestrictedModelsError` on
   `typesafe-ai/jev`, "Free tier users do not have access to this model", confirmed twice minutes
   apart. A model-entitlement refusal, not an auth failure, so the alternate key the skill checks
   would not have helped. N-53. **The standing grant to run models via `127.0.0.1:4000` does not
   cover it, because Jev is a hosted evaluate endpoint and no person owns a provider
   entitlement.** Consequence: no persisted Jev artifact exists for E1, E3 or E4, which are three
   of the five calls the handoff reserves for it. Every E1, E3 and E4 decision in this batch is
   unreviewed by dissent.
2. **M4's clean baseline.** Not an external outage. The free-route model narrates its work when
   the prompt carries observations: eight rows gives 5732 characters, three gives 5268, a withheld
   string 8167, and **no rows 167**. The 512-character cap falls between the derivation and the
   payload. Raising the cap was run live at 4096 output tokens and parsed 1 of 5. All three
   options are measured; none works. `PROSE` (`inv_r1_m4_baseline/`, `inv_r1_m4_design/`).
3. **E2's mechanism contrasts, second run.** Not externally blocked. The observable was rebuilt
   and the re-run produced ties and non-responses, which is a result rather than a gap.
4. **E3's post-fix ladder.** Not externally blocked. It is a one-command re-run of
   `s09_e3_selection.crossover()` against code that is already fixed. It has not been done.
5. **E4's live campaign.** Not externally blocked and deliberately declined on the evidence.
6. **The full suite on a clean box.** Not run. N-46 shows the environment makes the number
   unreadable, and N-42 shows the previous "0 failures" was `grep -c '^FAILED'` reading a `-q` log.
7. **The 62 settlement test files pending N-30.** Not run, and not blocked by anything external.

---

## 3. Decision table: research question to architectural implication

One row per question, verbatim from `WORKER-STAGE-09-PARALLEL-EXPANSION.md` lines 15-19. The
"result" column states what the evidence supports **at this tip**, including where that is
"nothing yet".

| # | Question (verbatim) | Intervention | Result | Evidence | Architectural implication |
|---|---|---|---|---|---|
| 1 | "Which representations can a model acquire and execute, and which fail because of language limits, construction difficulty or runtime defects?" | The same decision written in three notations and run under one `ComparisonConditions` with one query budget of 8. Boolean world via `ComparisonConditions.world`; ordering world via `episode_runner(name)`. | Boolean: all 15 cells `comparable`, step and ast agreeing to the digit, graph returning `None` on two because its `commit` guard reads one observed bit and falls through to `stop`. Ordering: all 15 `comparable`, in exact agreement, **all at 0.0**. SWE: `python-step` only; 24 families x 4 lineages, 156 instances; before-picture retracted, ceilings lifted, `probe_reach` 30/30 held-out. | `reports/evidence/inv_r1_e1_matrix/matrix.json`, `inv_r1_e1_ordering_matrix/RESULT.md`, `inv_r1_e1_swe/matrix.json`, `inv_r1_e1_swe/RESULT.md` (INVALID banner), `inv_r1_e1_swe_ceiling/RESULT.md` | **Each world owns its action validator and its executor**, rather than teaching one executor a second vocabulary. That is what made a second world reachable, and it is the established shape. The remaining limits are **node-set and view limits, not plumbing**: the typed AST cannot compare two jobs symbolically, and the SWE view cannot be projected to eight fields without dropping the program under repair. |
| 2 | "Does accumulated experience improve acquisition and later action choices? Does relevant experience help more than irrelevant or shuffled experience?" | Five contrasts on the `diagnostic` field, then all five re-run on a scored observable that executes the returned policy. Arms: relevant experience (3 graph seeds), no experience (0 observations), size-matched irrelevant (3 software seeds). | **Negative, and the negative is the strongest result in the batch.** All three arms score 1.0 and 0.0 on evidence. `readings.json` holds three arms byte-identical on all six keys, all `selected: seed-sw-ddmin`. Four of five contrasts are ties or non-responses against an observable verified to separate a reader at 2.0 from an identical blind policy at 1.0. The apparatus discriminates; the acquisition does not use it. | `reports/evidence/inv_r1_e2_scored/readings.json`, `inv_r1_e2_scored/CONTRASTS.md`, `inv_r1_e2_challenge/RESULT.md`, `inv_r1_e2_noexp/RETRACTED.md`, `inv_r1_e2_relevance/RETRACTED.md`, `inv_r1_e2_transfer/RETRACTED.md` | **The instrument is not the blocker and the prompt is not the blocker.** A dependent variable that echoes its input cannot support a claim that the input influenced the output, and every one of these contrasts had that shape. The next change belongs in **acquisition**, not in evaluation: a two-item method menu with a default cannot show a choice, and the default is now gone, so the menu is observable. What is still missing is a reason for the model to condition on what it was shown. |
| 3 | "Does retained behavior help on new task families or domains after its acquisition cost is included?" | Retained against cold reacquisition, both spending 5 use dispatches, separated only by the construction dispatch, priced from the cap sheet. Separately, 3 acquired use records run out of process on within-world and transfer software tasks. | **Cost: crossover at 5 uses** (16345 against 19614 units; 3269.0 against 3922.8 per use). **Behaviour: one transfer instance at 0.300**, the weakest of the three executed records. Source-to-target adaptation is a tie on one task with one dispatch per arm. | `reports/evidence/inv_r1_e2_retention/costs.json`, `reports/evidence/inv_r1_e2_scored/remaining-contrasts.json` (keys `transfer` and `retention`), `reports/evidence/inv_r1_m3b/use_records.json` | **Retention is a cost mechanism and should be budgeted as one.** The crossover is `construction_price / use_price`, so it moves with either and must be recomputed per campaign rather than carried as a constant. The 33 refusals in run 8 were scope and empty repertoires, not defects: **acquisition yield, not a broken boundary.** |
| 4 | "Can the system choose useful investigations from its own failures and results, rather than follow a human-authored task sequence?" | Adaptive `agenda_policy.AgendaPolicy` against `agenda_policy.FixedPolicy` under one envelope each, on three worlds at six budgets, measuring the four frozen yields. The control was fitted by exhaustive search over 196 rule pairs (2 methods x 2 methods x 7 depths x 7 depths), verified by `tests/test_s09sel_divergence.py:150-160`. | **Treatment active, and the committed ladder is pre-fix.** The sever control (24 cells, post-fix) establishes causality on executed evidence. The divergence case shows both policies choosing differently from the same portfolio. The store path is fixed: 5 operations written by the run itself, and `science_unchanged` records every frozen measure byte-identical to the pre-fix run. **But `e3-crossover.json` predates the `crossover()` fix and was never regenerated**, and the post-fix sever control shows the control's held-out advantage *growing* (0.000 at 14 and 20, 0.359 at 40, 0.391 at 60) rather than the saturation the retraction described. | `reports/evidence/inv_r1_e3_selection/e3-crossover.json`, `e3-divergence.json`, `e3-sever-control.json`, `e3-admitted-operations.json`, `e3-store-witness.json`; `experiments/ad01/s09_e3_selection.py:141-151` | **Decisions must reach real admitted operations, and they now do.** The shape that made this provable is the sever control, and the shape that made it invisible was a stateful policy instance shared across worlds. **A harness that shares a mutable object across independent cells will manufacture a result out of its own bookkeeping**, and that is a lesson about the study, not about selection. The remaining question, which this evidence does not answer, is whether the agenda chooses *better* or only *more*. |
| 5 | "Can it acquire an executable revision of its learning procedure that improves a later acquisition cohort? A better task solver alone does not answer this." | The intervention boundary is `imp_source`, which picks a probe input; `drive_improve_round` spends it; the output bit selects the descendant package. Headroom measured three ways: the estimator, a paired population measurement, and a ceiling over all sixteen inputs. | **Negative, on a measurement that can discriminate, with one caveat that must travel with it.** Apparatus qualified over 24 seeds (known-effect +0.2596, no-op 0.0, disconnect 0.0). Reachable descendant set {3, 11}, paired difference -0.00138, se 0.00123, z = -1.12 at N=1500, 4619 seeds to resolve. Ceiling over every input the instrument accepts: 0.00267, all sixteen means between 0.0588 and 0.0609. The earlier -0.0222 was a property of the estimator and `best_beats_incumbent` is true. No live campaign was run. | `reports/evidence/inv_r1_e4/headroom.json` (keys `controls`, `population`, `ceiling`, `qualification`, `headroom`); `experiments/ad01/improve_channel.py:615`; `tests/test_s09_e4_channel.py`; `tests/test_s09_e4_evidence.py` | **Do not spend a campaign on this channel until the descendant scoring itself is changed.** Choosing a better probe is the only lever this channel has, and that lever is exhausted at 0.00267. N-26 (`informs_decision: True` with `selected_evidence: [[]]`) must be fixed at the first consumer, and the pinned -0.0222 in `tests/test_s09_e4_channel.py` should be unpinned before the estimator is, so the test stops protecting a known-defective number. |

---

## 4. Ranked next conceptual decisions

Ranked by what constrains the most downstream work, not by what is cheapest or most interesting.
Each carries the question, the options, the evidence that would settle it, and what it costs to
be wrong. **No option is recommended.** The handoff forbids choosing an architecture to
manufacture progress, and a ranking that ends in an architecture is a recommendation wearing a
disguise.

### Rank 1. Is the next result allowed to depend on the acquisition claims that N-36 makes unsafe?

**Why first.** N-36 is critical and open: a policy that can read the repository recovered an
invertible task seed in 959 ms through a real launcher, and `launcher_local.py:12` says in its own
docstring that it is not containment. Every acquisition result in this batch rests on task
identifiers being opaque to the policy. This decision is upstream of all six buckets, because it
determines whether *any* of them is a claim about the model or a claim about a model that read
the answer key.

- **Options.** (a) Containment change: the key injected into the container rather than mounted in
  the repo, or held outside the tree. (b) A threat model that declares the learner cooperative
  and records it, leaving N-36 open as a known limitation. (c) An unenumerable seed space, so
  enumeration is not the attack. (d) Defer: no acquisition claim is made until it is settled.
- **What would settle it.** One measurement: run a real policy through the real launcher, hand it
  the repository, and time the seed recovery under each option. Option (a) should be measurably
  slower than 959 ms; option (b) settles nothing and should be recorded as a decision rather than
  a result.
- **Cost to be wrong.** Highest on this list. Wrong here and the whole batch's acquisition,
  utility and transfer claims are a measurement of a reader. The status report already concedes
  this; the roadmap should not have to.

### Rank 2. What is the study allowed to call the result of a pre-fix artifact?

**Why second.** E3's committed ladder is produced by pre-fix code and the branch's running
summary reads as though it is not. The handoff's line 107 is explicit that a final prose-only
commit can follow the tested source "if that distinction is explicit", and the handoff's line 73
requires decisions to "reach real admitted operations rather than appear only in an agenda log".
A stale artifact in a frozen-evidence tree is the failure mode that produced today's nine
retractions.

- **Options.** (a) Re-run `crossover()` now and replace `e3-crossover.json`, keeping the pre-fix
  file under a retraction directory as history. (b) Keep both and label the pre-fix one as
  pre-fix in the ledger. (c) Delete the pre-fix artifact and rely on the sever control, which is
  post-fix and covers 4 of 6 budgets.
- **What would settle it.** None of these needs a decision. The re-run is one command against
  already-fixed code. **This rank is here because the ranking itself is the decision**: whether
  the next batch may cite `e3-crossover.json` at all.
- **Cost to be wrong.** A published E3 number that the fixed code does not reproduce is the same
  class of defect as the retracted SWE zero and the retracted E3 saturation explanation. Both
  arrived as clean numbers from broken harnesses.

### Rank 3. Is "one acquisition cohort, no replication" a claim the branch is allowed to make at all?

**Why third.** The handoff's line 67 requires at least two independent campaign namespaces for a
replication where the first valid campaign leaves supported arms. E2 ran one. Every E2 result is
therefore single-cohort, and the E2 result is a negative, which is the class of finding that most
needs replication and least gets reviewed.

- **Options.** (a) A second namespace for E2's scored observable, sharing no mutable state and no
  assessment feedback. (b) Declare E2 descriptive-only and carry no inferential claim, per the
  handoff's multiple-comparison clause. (c) Rerun the invalid apparatus campaign; the handoff
  explicitly says this does not count as scientific replication.
- **What would settle it.** A second namespace on the same scored observable. The observable is
  built and discriminates; a namespace is a configuration, not a rebuild.
- **Cost to be wrong.** A negative from one cohort is a hypothesis, not a finding. Publishing it
  as a finding is the specific overclaim this branch has already made twice in the same week.

### Rank 4. Does the acquisition path need a reason to read its evidence, or a menu that makes ignoring it expensive?

**Why fourth.** E2 is the deepest negative in the batch and the most actionable. Four of five
contrasts are ties or non-responses against an observable verified to discriminate. The menu
default has been removed, so the choice is observable. The model now chooses `seed-sw-ddmin` and
does not vary with the evidence.

- **Options.** (a) A menu where the correct choice is not first, so the default argument does not
  resolve it. (b) A construction path that requires the policy to commit a probe choice before it
  sees outcomes, making the commitment observable. (c) A larger family panel where the model is
  sometimes wrong, so a prior is not sufficient. (d) Accept the negative: this substrate's model
  does not condition on observations, and that is the finding.
- **What would settle it.** Option (a) is measurable at near-zero cost: shuffle the menu order
  and see whether `selected` moves. If it does not, options (b) and (c) are the only remaining
  explanations and the next measurement is bounded.
- **Cost to be wrong.** Moderate. Choosing (d) when (a) would have worked discards a cheap
  experiment; choosing (a) when (d) is true spends one campaign proving a prior.

### Rank 5. What is the SWE world's status, given that its machine-readable after-picture does not exist?

**Why fifth.** The ceiling lane's `RESULT.md` cites a `matrix.json` in its own directory for the
per-family repair counts, and that file has never existed in git. The before-picture carries a
retraction banner. So the SWE evidence chain is: a retracted before-picture, a prose after-picture
with no artifact, and 104 test definitions guarding the instrument.

- **Options.** (a) Regenerate and commit the ceiling matrix before the branch reports. (b) Treat
  the SWE result as prose and downgrade every SWE claim to `PROSE`. (c) Re-run the SWE matrix from
  the current tip, which also picks up whatever changed since.
- **What would settle it.** Option (a) is a single generator run. The decision is whether it is
  in scope for the next batch or whether the SWE result ships as prose with a flag.
- **Cost to be wrong.** The SWE result is the batch's most positive-sounding number and it is the
  one with the weakest artifact chain. Shipping it unflagged is how a retracted number comes back.

### Rank 6. Should the E4 channel be measured at all, or is the decision "the descendant scoring is not the thing to vary"?

**Why sixth.** E4 is complete as a negative, but the negative is about a frozen instrument's input
menu. A decision that changes what a descendant *is* is invisible to that measurement, and N-63's
own `best_beats_incumbent: true` is evidence that the earlier headline was the estimator's
property, not the substrate's.

- **Options.** (a) Accept the negative on the frozen channel and stop. (b) Redefine the
  intervention boundary to something that changes descendant scoring, which is a substrate
  decision, not a study decision. (c) Widen the probe menu, which N-63 argues cannot help because
  the ceiling is over every input the instrument accepts.
- **What would settle it.** None of these, yet. The decision cannot be made until someone
  specifies an intervention boundary that is not a probe choice. **Say so explicitly: this is the
  one rank in this list where the honest answer is "not until a specific measurement exists", and
  the measurement is a written description of a non-probe learner decision plus its measurable
  effect on descendants.**
- **Cost to be wrong.** Low on the study, high on the architecture. Reading "no headroom" as
  "no possibility" closes a direction that may be open, and it closes it in a document that will
  be read as authoritative.

### Rank 7. Should the ledger's open severities be re-decided, and by whom?

**Why seventh, and last among the conceptual ones.** The ledger names its own unreviewed
judgements in a section titled "Structural choices in this pass that no dissent reviewed": N-01's
recorded severity, N-02 and N-03's conflict resolutions, N-28's causation, which rows got a
source check, and the definition given to the word "recheck". Four severities are open at critical
or blocker: N-01, N-23, N-24, N-53.

- **Options.** (a) Re-decide them on a branch where Jev works. (b) Re-decide them by the
  researcher, explicitly accepting that they are unreviewed. (c) Leave them open and carry the
  uncertainty in every downstream document.
- **What would settle it.** Option (a). Nothing in this repository can settle a judgement about
  what a finding's severity should be, and the ledger's author said so.
- **Cost to be wrong.** Moderate and diffuse. A critical finding recorded as high stops being
  worked on; the ledger's own author flagged this as "the severity is the load-bearing part".

---

## 5. What would falsify each headline result

Adversarial, and about this branch's own conclusions. Each entry names the observation that would
break the claim.

**"E2 is complete and the negative is real."**
- *Falsifier:* a second campaign namespace produces a non-tie on the same scored observable. One
  namespace is one sample, and a null on one sample is a hypothesis.
- *Falsifier:* the scored observable is re-checked and does not discriminate. The 2.0-against-1.0
  claim rests on a control pair in `inv_r1_e2_substitution/RESULT.md`, and the ledger's own
  finding N-39 says the scorer cannot distinguish a timeout from a real refusal. A "no response"
  is therefore also what a timed-out step looks like, and the E2 non-responses are exactly a
  "no response".
- *Falsifier:* the removal of the method default is itself the treatment. Removing `ddmin` from
  the signature changed the menu; it did not change why the model picks the first eligible member.

**"E3's treatment is active and the sever control establishes causality."**
- *Falsifier:* the severed arm's strict-prefix property holds because the sever is applied
  downstream of the decision rather than at it. The control shows a difference in *what ran*, not
  that a different *decision* was causally upstream of the effect. A sever that removes execution
  after the decision point would produce the same 24-of-24 vanishing.
- *Falsifier:* the post-fix sever control contradicts the committed ladder's direction, and I have
  shown it does. The control's held-out advantage grows with budget in the fresh-policy data while
  the committed ladder shows it flat then falling. **Both artifacts are on this tip, they were
  produced by different code, and the older one is the one every report cites.**
- *Falsifier:* the store wiring changed no number *because* the store is not on the measurement
  path. `science_unchanged` is a strong result, but it is also what you would see if the dsn
  reached a code path the yields never read.

**"E4 has no headroom."**
- *Falsifier:* an intervention boundary that is not a probe choice moves descendants. The
  measurement covers the input menu of a frozen instrument and nothing else.
- *Falsifier:* `best_beats_incumbent: true` (0.0667 against 0.0222) is the falsifier already
  recorded, and it is why the earlier headline was withdrawn. Any report that restores
  "the best reachable probe scores below the incumbent" is falsified by the artifact's own field.
- *Falsifier:* 4619 seeds resolve the -0.00138 paired difference. That is a reachable number.
  "The substrate has no headroom" is over-stated relative to "the reachable pair does not differ
  at 1500 seeds".

**"E1's SWE representation repairs most reachable instances."**
- *Falsifier:* the per-family counts. They are in a `matrix.json` that does not exist. The claim is
  prose with a reach table (30/30) and no repair-rate table behind it.
- *Falsifier:* the derived budget reads `record["patch"]`, the assessor's answer. The defence
  (it hands the arm nothing, it errs toward not flattering the result, it is pinned by two
  contamination tests) is the lane's own and is unreviewed. The ceiling lane itself named this as
  its second question for Jev. **A derived budget that reads the answer is standard practice, and
  it is also the kind of thing that is only safe while someone is arguing for it.**
- *Falsifier:* the ten unrepaired instances are a property of the panel, not the solver. Five
  `swapped_window` instances need a two-part repair no single-line search can reach, and
  `stale_accumulator` needs text the faulty program does not contain. If the panel is the problem,
  the representation is being measured on tasks it was not built for.

**"Retention pays for itself after 5 uses."**
- *Falsifier:* the price moves. The crossover is `construction_price / use_price`, and the unit
  price is 3269 from a cap sheet. CS-01's whole repair was that these are different currencies, so
  a crossover derived from one of them is exactly the arithmetic that repair warns about.
- *Falsifier:* the retained arm's five uses are all on the same repertoire. The crossover prices
  *reusing* bytes, and it says nothing about using them on a task the acquisition did not see.

**"E1's three representations agree on the ordering world."**
- *Falsifier:* all three score 0.0. Three arms agreeing on zero is a parity result *and* a ceiling
  result, and a reader who takes only the first will claim representations are interchangeable.
  Jev already scored the portability claim at 0.00.

**"The instrumentation is trustworthy enough to make a null interpretable."**
- *Falsifier:* N-36. A seed recovered in 959 ms through the real launcher means the instrument
  leaks the answer to the thing it is measuring.
- *Falsifier:* the tests protect the defects. `tests/test_s09_e4_channel.py` pins the -0.0222 the
  ledger calls incapable of being positive. A suite that pins a known-broken number is a suite
  that will report green on the broken thing.

---

## 6. Ledger and roadmap state

**Ledger.** `reviews/STAGE-09-FINDINGS.md`, N-01 through N-64 plus CS-01 through CS-03, four
deliberately red tests, and four non-defect findings the schema does not fit (N-42/N-46, N-53,
N-31's split verdict, N-26's headroom figure). Open at critical or blocker: N-01, N-23, N-24,
N-53. N-51 is closed by artifact and the ledger's own row needs updating: it currently records
`operations_written_by_the_run` as 0 in both arms, which was true at 07:54 and false at 09:26.
The sever control and `science_unchanged` are not in the ledger at all.

**Roadmap.** `reports/STAGE-09-ROADMAP.md` is this file. It replaces nothing; the researcher
owns `reports/STAGE-09-CONNECTED-STATUS.md` and `reports/STAGE-09-DECISION-TABLE.md` and will
rewrite both from it.

---

## 7. Where the sources contradict the brief

Five places. In each the source wins and the disagreement is named.

1. **"E3's numbers are post-fix."** They are not. `e3-crossover.json` was written at `02ce64b`
   (01:28) and the `crossover()` policy-per-budget fix **never landed at all** — `52235a6`
   (07:57) fixed `sever_control()` instead, and `crossover()` is byte-identical at HEAD (ledger
   N-413). The store path
   *was* fixed, and `e3-admitted-operations.json` (09:26) shows 5 operations written by the run
   with every frozen measure byte-identical. Both halves of the brief's sentence are half right in
   a way that matters: the store is fixed, the ladder is not, and the ladder's defect is still
   live in the code. The post-fix ladder is at `reports/evidence/inv_r1_e3_ladder/`.
2. **N-51's ledger row is out of date.** It records
   `reports/evidence/inv_r1_e3_selection/e3-store-witness.json`, written 07:54, where
   `operations_written_by_the_run` is 0 in both arms. The later
   `e3-admitted-operations.json`, 09:26, records 5 in the connected arm and 0 in the severed. The
   row says "N-51 CONFIRMED" on the earlier artifact. Its conclusion (the run writes nothing) was
   true when written and is false now. **The other lane owns that file and should update it; I
   have not touched it.**
3. **The E3 saturation explanation is not merely retracted, it is contradicted.** The post-fix
   sever control shows the control's held-out advantage growing with budget (0.000 at 14 and 20,
   0.359 at 40, 0.391 at 60 at world-aggregate level), not a six-wide schedule running out at 20.
   The status report's line 191-199 explains the two-sided result by control saturation; that
   explanation is an artifact of the shared policy instance, and the fixed data points the other
   way. **The no-benefit conclusion is unaffected and still correct. The reason is different, and
   the new reason is not yet measured.**
4. **The ceiling lane's `matrix.json` does not exist.** `RESULT.md` cites it four times, including
   for "the exact per-family counts". `git log --diff-filter=A` shows it was never added. The
   brief's "the qualifying instrument is now built and run" is true of the instrument and of
   `probe_reach`, and unbacked for the repair rate.
5. **`experiments/ad01/software.py` does not exist; the data-only world is elsewhere, and the
   `swe` world is now registered.** The data-only state machine the handoff excludes at line 47
   lives at `experiments/representation/software.py:1-3`, whose docstring reads "Tasks are DATA
   (plain JSON dicts), never host-executed programs." Separately, `s09_arm_parity._WORLDS` now
   holds `swe` as a third key alongside `boolean` and `ordering`, with a comment at
   `experiments/ad01/s09_arm_parity.py:39-48` saying it is registered "for addressability, not
   because the harness can normalise its view". The status report's claim that `episode_runner`
   "raises for any name but `boolean` and `ordering`" is therefore stale, and the brief's summary
   of the exclusion names an `ad01` path that does not exist.

**Also worth recording, not a contradiction:** two E3 artifacts of the same measurement disagree
in the fourth decimal place. `e3-divergence.json` records the agenda's held-out reduction at
budget 14 as `0.08465608465608465`; `e3-sever-control.json` records the same policy, world and
budget as `0.0847`. Same `measure_digest`, same code path, two rounded and two unrounded values.
Harmless on its own, and worth a check before either is quoted to a decimal.

---

## 8. What this document could not determine

- **Whether E3's agenda is genuinely better or only more active.** The post-fix ladder does not
  exist. I did not run it, and running it is one command against fixed code.
- **The SWE repair rate.** The artifact that would carry it does not exist. I did not regenerate
  it.
- **Whether the E3 control's held-out advantage is real.** The fresh-policy sever control suggests
  it is, and the committed ladder suggests the opposite. Both are on this tip.
- **Whether N-03's `loop.py:199` fold is reachable.** The ledger says this needs a caller trace
  and marks it unsettled; I did not trace callers.
- **The 18688 unit figure — SETTLED, and it is a sizing, not a liability.**
  **Resolved at `94443a7`; derivation in
  [`reviews/STAGE-09-N36-N65.md`](../reviews/STAGE-09-N36-N65.md).** The earlier
  entry here said the figure was "in no artifact anywhere in the repository".
  That was wrong, and it was wrong because the search looked for a JSON file.
  **18688 is `4 × 2294 + 4 × 2378`**, the per-request prices in the test bodies
  that introduced it at `f3af21a`, and `broker.exposure_schedule` recomputes
  both prices from the per-prompt character counts those same tests record
  (`{980, 981}` → 2294, `{1318, 1319}` → 2378, at the freeze's own
  `max_output_tokens: 2048` and `automatic_retries: 0`).

  The `8 × 2336` shape is also exact, and that is the trap: 2336 is the
  arithmetic mean of 2294 and 2378. There was never a per-dispatch price of
  2336 and no campaign was priced at one, so the deduction from "eight
  dispatches" to "2336 each" does not hold. The eight requests had two
  different prices.

  The currency is broker **reservation units** in `estimated-budget` terms
  (`broker.py:137`), the same type `ReservationAllowance` carries — a
  pre-flight campaign sizing, which is exactly what that type's docstring says
  it exists to produce. **It is not held exposure.** The figure that is both
  held and unsettled remains **2294**, in r4's
  `store-reconciliation.json`, whose `reservation_amount: 2294` sits on an
  operation id naming a **P1** request — the schedule price for P1. The store
  and the schedule agree, from two artifacts written by different code paths.

  So neither horn of the old dilemma holds: the documents did not overstate
  liability by 16394 units, and no artifact was missing. They mislabelled a
  campaign sizing as held liability. The correction is to stop calling 18688
  liability, not to subtract it from anything.
- **Whether any of today's retractions would survive Jev.** Jev returned 403. I did not call it,
  did not build a substitute, and did not invent a score.

---

## 9. Judgements in this document that no dissent reviewed

N-53 is open and I did not call Jev. These are mine, and they are the ones that would have gone
to it:

1. **Ranking N-36 first.** I ranked containment above everything else on the grounds that it is
   upstream of all six buckets. A dissent would reasonably ask whether an unenforceable threat
   model is worth a rank-1 slot when no current result depends on a live adversarial policy.
2. **Calling the E3 sever control post-fix evidence and reading its direction against the
   committed ladder.** I aggregated the sever control myself. The aggregation is arithmetic over
   a committed artifact, but the choice to read it as the better measurement is a judgement: it is
   post-fix, and it is the only post-fix E3 yield data on the tree.
3. **Treating a missing `matrix.json` as a rank-5 decision rather than a defect to fix tonight.**
   That is a scoping call about someone else's lane's deliverable.
4. **The falsifier list.** Every entry is adversarial toward this branch, but adversarial is not
   the same as correct, and no independent lane checked that the falsifiers are the *right* ones.
5. **The decision not to recommend an architecture.** The handoff requires it and I have honoured
   it, but the consequence is that rank 4 and rank 6 both end in "the options are these and the
   evidence picks none". A reader may reasonably want a recommendation with the reasoning attached
   and the decision named separately. That is a presentation difference, not a substantive one, and
   I chose the one the handoff asks for.
