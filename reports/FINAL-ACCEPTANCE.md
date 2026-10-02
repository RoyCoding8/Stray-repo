> Historical pass report. Its mechanism verdict was **overturned by an
> independent review** after this pass returned it, and both halves of that
> over-claim were then repaired (X3, X4b). Current scoped status is reconciled
> in [PROJECT-LEDGER.md](PROJECT-LEDGER.md) and
> [STAGE-09-10-COMPLETION-MATRIX.md](STAGE-09-10-COMPLETION-MATRIX.md). Read
> this file for what this pass measured and how; its dispositions do not govern
> the current checkpoint.

# Final independent acceptance — consolidation batch 2026-10-01

Acceptance pass over `codex/stage09-consolidation-2026-10-01` at `794737f`,
base `70223fb`. Over that base, 85 commits and 33 merges, naming **31 distinct
lanes** plus the two search passes. The two campaign totals in the whole
history at `794737f` are 221 commits and 67 merges. Two live campaigns, two
search passes, one integrated-tip repair lane pair (X1, X2). I authored none
of it.

*(The 221 commits and ~53 lanes figures this paragraph originally carried do
not survive a recount. `git rev-list --count 794737f` is 221, which is the
whole history rather than the batch, and no derivation of 53 lanes exists at
this tip under either a merge-subject count or a distinct-branch count.)*

Verification was done against artifacts and source, not against lane
reports. Where a report and a file disagreed, the file decided. Four
headline numbers were recomputed from the evidence directories and from live
source rather than re-read, and three further properties were probed by
scripts I wrote for this pass.

Runtime: WSL Ubuntu, real PostgreSQL, `PYTHONPATH=src` into
`/home/ubuntu/.venvs/as9`, `SETTLEMENT_CLAIM_LEDGER` under `/home/ubuntu`.
No live model call, no network, no paid route, no Jev.
`S09ISO: dropped N database(s)` is normal.

---

## Headline verdict

**This batch established a real causal path — durable identity, mandatory
authority, a freeze guard that is correct against the parse but gates no
production path, one mission owner, and two search passes
that found and fixed four live production defects — and established no
acquisition, no learning advantage, no transfer and no learner
improvement.**

---

## The six dispositions, each with its own verdict

### 1. Mechanism — CONFIRMED, with one limit

The machinery does what it claims. Every arrow of the milestone-A chain
resolved to a durable row, and the machinery holds under tamper.

Evidence. `tests/test_inv_a_chain.py`, `test_inv_a_counterexamples.py` and
`test_inv_a_reviewer_source.py` pass together (`29 passed in 43.81s`), and
the seven tamper cases each run a clean baseline in the same test on the
same store before the tamper. I read the baselines rather than the summary:
case 2 executes the real member through the real broker and asserts
`settled is True` before the substitution refuses; case 5 settles a body
that arrived `success` before settling an empty body `failure` under a
different receipt identity; case 6 runs the chain program first and asserts
one episode with `disposition = inspected` before the hang and the
budget-exhaustion cases. I count **four** tamper cases whose baseline is a
real green execution, above the three the assignment asked for.

Authority is a type, not a branch. I confirmed by attribute that
`REACHABLE_EVIDENCE`, `MENU_EVIDENCE`, `_STRATEGY_SOURCE` and `_menu_probe`
no longer exist on `improve_channel` (C4 deleted the fixed menu rather than
widening it), and that `run_step_out_of_process` /
`run_member_out_of_process` carry no `dsn is None` branch.

The freeze guard is correct against the parse, not a hand-kept list. I probed
`improve_channel._attempts_frozen_write` directly with 19 binding forms I
wrote myself: subscript assign, augassign, delete, annassign, subscript of
subscript, chained subscript, bare name, annassign, walrus, `for` target,
`del`, attribute, `setattr`, `exec`, comprehension target, `except as`,
`with ... as` — all refused; a read (`x = view["grant"]`) and a write to a
non-frozen key (`view["harmless"] = 1`) correctly admitted. **Zero
mismatches.** One of my initial 19 expectations was wrong (`with view["grant"]
as g` loads rather than stores); I corrected my expectation, not the guard.

**What that probe does not say, and a reader must not infer from it.** The
guard is correct; it is not on the path a live improver takes.
`admit_revision_under_freeze` has one non-test caller,
`learner_revision.acquire`, and that function has no production caller
(`git log -S` finds none in history). A model-authored improver enters at
`live_construct.parse_and_build_live_package` (shipped caller
`scripts/invl02_live.py:1987`) under `method_exec.verify_step_source` alone.
Measured, the same bytes that the freeze refuses — writing `view["grant"]` and
`view.update({"grant": ...})` — are **admitted** by `verify_step_source`, and
the live `IMPROVE` view carries none of the six frozen field names, so there is
no live frozen write for the guard to catch. Wiring the guard into the live
path would refuse free-form replies (measured `changes-an-unauthorised-decision`
and `task-solver-not-decision`) while all four authored controls stayed
eligible, which is the opposite of what milestone C intends. The guard is
correctly dead and is not described as enforced from here on. The *other* half
of the same repair, X4b's `effect_id` bound to a settled `operations` row, **is**
on a live path (`improve_channel.py:2234`, via `drive_improve_round` and
`run_live_improve_round`), so the two halves are not described alike. Full
evidence in the freeze-wiring note of
[STAGE-09-10-COMPLETION-MATRIX](STAGE-09-10-COMPLETION-MATRIX.md).

Limit. A **computed** subscript key is not resolved, by decision, and the
guard says so. `view[some_var] = x` where `some_var` binds `"grant"` passes
the static check. The dynamic before/after comparison in
`admit_revision_under_freeze` is the layer that catches it. The freeze is
one layer deep, not two.

### 2. Acquisition — NEGATIVE. Nothing usable was acquired.

Honest negative, recorded with real provenance rather than absent.

- **B12 (current SWE construction run): 0 of 4 lineages.** I recomputed this
  from `campaign.json` and `store-rows.json`, not from the summary.
  `acquired_lineages` 0, `independent_acquired_lineages` 0,
  `distinct_acquisition_digests` 0, `lineages_attempted` 4,
  `no_acquisition_lineages` 4. Every one of the four
  `lineages[i].acquisition_digest` is `null`. All four `use_rows` carry
  `outcome: "no-acquisition"`, `episodes: 0`, `repairs: null`.
- **The retained-method leg: 0 of 3 members measurable over 27 executions.**
  Recomputed: three members, 9 rows each, 27 rows total, 1 acquisition-task
  row carrying a null verdict, 26 comparable rows. The union of verdicts
  across all 26 is exactly `{"preserved"}`. `same_reduction_as_seed` is
  `True` on **26 of 26**. `retained_method_leg_measurable` is `false` on
  all three. The four strategy probes are also 0 of 4, all
  `distinct_verdicts: ["preserved"]`.
- The r4 archive remains the only route acquisition whose bytes were kept,
  and it earned 3 of 6 arms. `b12_swe` earned 0 of 4. Both numbers are
  carried into the artifact and neither is the artifact's to improve on.

This is a bounded zero resting on a rate, not a proof the route cannot
acquire. The artifact says so in its own `not_claimed`.

### 3. Utility — NEGATIVE. No learning advantage. There is no learned arm.

Plainly: **no learning advantage exists, and none could be measured on this
batch**, because B12 acquired nothing and a failed acquisition is never
promoted to an authored learned arm. The assignment forbids exactly that
promotion, and the artifacts honour it: `acquired_artifacts` is asserted
`[]`, `retained_use` is `None`, and no authored substitute appears.

Nothing here should be read as a mechanism result becoming a utility
result. The mechanism is confirmed; the utility question is unanswered
because the input to it does not exist.

### 4. Transfer — NEGATIVE, and the archive has no usable members.

Two independent zeros.

- The retention leg: 0 of 3 live-acquired members carry a varying verdict
  over 27 executions. Retained reuse was never measured because nothing
  retained was distinguishable from the seed.
- The two-domain crossing (C7) transfers **a predicate, not answers**, and
  the lane says so. A Boolean probe returns four output bits about a hidden
  function; the SWE side has no way to spend that vector. What crosses is
  the distinction "expected differs from actual, and the result is well
  formed, so this is a value fault and not an error", applied to classify
  the SWE side's own mismatching public tests.

By the assignment's own rule, an archive with no usable members is a
no-acquisition result, not transfer evidence. **Transfer is not
established.**

### 5. Autonomous selection — NOT ESTABLISHED. The order is scripted.

The C7 crossing runs **three Boolean episodes then three SWE episodes**, a
fixed sequence written in `experiments/ad01/twodomain.py`. That is a script,
not a program choosing from the admissible frontier. The lane does not claim
otherwise, and it is honest about what its demonstration is.

Worse for a comparison, and measured: **the crossing is powered on one side
only.** I recomputed `twodomain.cluster_census()` from source. `boolean-rule-v1`
offers **1 cluster against 6 required**, shortfall 5, `powered: False`.
`software-fault-repair-v1` offers 9, `powered: True`.
`powered_structures == ['software-fault-repair-v1']` and
`crossing_powered` is `False`.

The single cluster is not a guess. I hashed the `hypothesis_class`
descriptor myself across `boolean_rule.SPLITS` × `range(24)`: **exactly one**
distinct descriptor, identical `class_digest`, `class_size`, `form` and
`n_inputs` for every split and seed. A contrast over it has one independent
unit however many tasks it runs, and no panel choice can move it.

**A two-domain demonstration is not a two-domain result.** The comparison
is unavailable from these two instruments as they stand.

### 6. Learner improvement — NEGATIVE. No eligible revision, no descendants.

No live revision attempt ran. `c4-live` is listed in the plan and has no
workstream report, no evidence directory and no test.

What exists is mechanism. C4 deleted the two-member fixed menu and made a
descendant inherit its parent's construction input, so `reachable_evidence`
is now a function of the program rather than a constant published beside
it. I confirmed `_revision_source(3)`, `(8)` and `(11)` all build sources
of ~1067 characters and all pass `_attempts_frozen_write` — the authorised
kind of revision stays eligible after X2 widened the guard, which is the
property that matters (a guard and its refusal suite cannot both pass by the
guard being broad). The control registries agree: `CONTROL_ROLES` is a
strict subset of `WRITTEN_CONTROL_ROLES`.

That is an inheritable mechanism with no revised descendant cohort. Per
WORKER-PROMPT.md, the prototype's existence does not claim beneficial RSI,
and I am not claiming it.

---

## Four recomputed numbers

Each was recomputed from the evidence directory and, where possible, from
live source in a fresh process. Not one was taken from a report.

| # | Number | Claimed | Recomputed | Agrees |
|---|---|---|---|---|
| 1 | Panel clusters and ceiling | `graph:dev+transfer` at 6 clusters, ceiling `0.285714`, required 6; three panels powered | I called `w2_retention_campaign.panel_combinations()` and diffed all 14 panels against the shipped census on 10 fields each: **0 disagreements**. Powered set is exactly `['graph:dev+transfer', 'graph:within+transfer', 'graph:dev+within+transfer']`. `minimum_clusters_for_alpha(0.05)` = 6, matching the protocol's `_required_clusters()` = 6. | **AGREES** |
| 2 | Retention leg, 0 of 3 over 27 executions | 3 members measured, 0 measurable, all `preserved` | 3 members × 9 rows = **27 rows**; 1 acquisition-task row (null verdict); **26 comparable rows**; union of verdicts = `{"preserved"}`; `same_reduction_as_seed` **26 of 26**; `retained_method_leg_measurable` false on 3 of 3. Strategy probes 0 of 4, all `preserved`. | **AGREES** |
| 3 | B12, 0 of 4, with sends reconciling to operations and receipts | 5 sends, 5 operations, 5 receipts, 0 acquired | 4 lineages, all `acquisition_digest: null`, all `no-acquisition`. **5 physical sends = 5 operations = 5 receipts**, every operation matched to exactly one receipt and one reservation. Reservation states recompute exactly: settled sum **10899** = `allocation.consumed`; uncertain sum **2700** = `allocation.reserved`. `_receipt_actual_cost` is `null` on all five and no `"billed": 0` appears anywhere. | **AGREES** |
| 4 | Boolean side, one hypothesis class | 1 cluster against 6 | `cluster_census()` from source: boolean **1**, required 6, shortfall 5, `powered: False`; SWE **9**, `powered: True`; `crossing_powered` False. Independently hashed the `hypothesis_class` descriptor myself across 3 splits × 24 seeds: **1 distinct descriptor**. | **AGREES** |

**No disagreement found in any of the four.** For a batch whose own second
search pass had already caught a false "only powered panel", this is worth
stating plainly: the numeric layer is sound. The defects I found are in the
documentary layer and in one unrun measurement.

---

## Skips by scope

Every run below was executed with `-rs`. **Zero skips in every run.**

| Run | Files | Skips | Scope of any skip |
|---|---|---|---|
| R1 | milestone A chain + counterexamples + reviewer source (3) | **0** | none |
| R2 | A identity / authority / lost-update / callers / probe / improve (7) | **0** | none |
| R3 | milestone B census, retention, SWE, budget, cap sheet (5) | **0** | none |
| R4 | B repertoire, view contract, replseed, constant score, graph driver, graph child, SWE view, X1 arity (8) | **0** | 4 errors, not skips; see below |
| R5 | milestone C freeze, fixture, construction, suspend, two-domain, mission, P1, P2 ×3, X2 (11) | **0** | none |
| R6 | acceptance findings (1) | **0** | 8 failures, not skips; mine, by design |

I also swept the 29 test files added by this batch for skip machinery
(`pytest.mark.skip`, `skipif`, `xfail`, `raise pytest.skip`): **zero
occurrences in any of them.** No new test in the batch can hide behind a
skip marker.

### Exact pytest summary lines, reported separately

```
R1  29 passed in 43.81s (0:00:43)
R2  80 passed in 41.44s (0:00:41)
R3  69 passed in 23.79s (0:00:23)
R4  81 passed, 4 errors in 310.04s (0:05:10)
R4b 7 passed, 4 errors in 196.78s (0:03:16)      [tests/test_inv_b4_constant_score.py alone]
R5  125 passed in 112.97s (0:01:52)
R6  8 failed, 5 passed in 2.03s (0:00:02)
```

**These are six separate runs and they are not summed.** R1 + R2 + R3 + R5
were green on disjoint file sets. R4 is not green: four tests **error** at
setup. R6 is red by design, because a defect I recorded has a failing-first
test that fails until the repair lands.

Each run appended `S09ISO: dropped 13 database(s) for this run`.

---

## Defects recorded, with failing-first tests

Five defects, eight failing tests, in `tests/test_final_accept_findings.py`.
**No production code was repaired.** Each test is a record for the next
repair lane.

### FA-01 — a stale "only powered panel" claim survives in two governing files

`reports/workstreams/b13b-replseed.md:123` reads "would read nothing on the
**only powered panel**". `reports/cap-sheets/b-live-cap.md:48` reads "The
three `graph` rows are the **only powered panels**".

Three panels are powered. `graph:dev+transfer` is the **smallest** of the
three, which is why B13 and B14 name it. Smallest is not only. Pass 2 found
this at `p2-search.md:94` and recorded it without editing, correctly, since
the file belongs to another lane. It was never fixed, and the batch
integrated with it live in the cap sheet that gates the live lanes.

Tests: `test_no_governing_document_claims_one_powered_panel[b13b-replseed.md]`,
`[…cap-sheets/b-live-cap.md]`,
`test_the_b13b_sentence_about_the_powered_graph_panel_reads_correctly`.

### FA-02 — a gate reads a freeze artifact that was never written, and the batch merged anyway

`tests/test_inv_b4_constant_score.py:313` sets
`FREEZE_PATH = "reports/evidence/invr1b4-mean-score/b4-crossover-mean.json"`.
That path **does not exist on this tree.** Four tests error at setup with
`pytest.fail` naming the missing file. I confirmed independently:
`ls reports/evidence/invr1b4-mean-score/` returns "No such file or
directory".

The lane declared this honestly — `b4-score.md` records the 894 s sweep was
cancelled for resource reasons, says "a cancelled measurement is not a null
measurement", and states the 4 errors are "the honest state of an
unmeasured freeze, not a regression". **The lane is not at fault. The batch
is.** It merged with four errors outstanding, and no completion report
names them.

Test: `test_the_b4_freeze_artifact_its_own_gate_reads_is_committed`.

### FA-03 — the plan's State column is entirely pre-merge and carries no information

`reports/PLAN.md` lines 45–61 mark six lanes `running` and ten `queued`, and
none `merged`, including `a1-preflight` which merged at `450a988` and whose
gate is green on this tip. Twenty-six workstream reports exist for lanes
the table does not carry at all: a4b, a6, a7, a8, b9, b12, b13b, b14, b18,
b1c, c3, c4, c6, c7, p1, p2, x1, x2.

Separately, `b5-sealed-state` and `c4-live` are still marked `queued` and
genuinely never ran. Naming them is right; the defect is that the column
gives shipped and unshipped lanes the identical marker, so it cannot answer
"what is outstanding". `c4-live` is the milestone-C deliverable
(WORKER-PROMPT.md §C) and cannot be dropped silently.

Test: `test_the_plan_names_the_lanes_that_actually_landed`.

### FA-04 — an archived generator reads a symbol C4 correctly deleted

`reports/evidence/inv_r1_e4/make_evidence.py:238` reads
`channel.REACHABLE_EVIDENCE`. Lane C4 deleted that symbol with the fixed
menu, which is the **correct** repair and the assignment's explicit ask.
The archived generator can no longer be run.

Recorded, not fixed: it is frozen history and nothing in this batch claims
the archived artifact must be regenerable. Flagging it because it is the one
place where the batch's correct deletions leave a dangling reader.

Test: `test_the_archived_e4_generator_cannot_run_against_the_deleted_menu`.

#### FA-04 as closed by the documentation lane: a second archived generator, and the family-prefix pattern

The acceptance pass named one archived generator. A second one carries a related
defect. **Both files are archived evidence and neither was edited.** The two
defects are *not* the same shape, and conflating them would be its own error:

| file | line | what it does | why it is now stale |
|---|---|---|---|
| `reports/evidence/inv_r1_e4/make_evidence.py` | 238 | reads `channel.REACHABLE_EVIDENCE` into its artifact | lane C4 deleted that symbol with the fixed menu, so the generator raises `AttributeError` and cannot run |
| `reports/evidence/inv_r1_e2_offline/make_evidence.py` | 242 | builds `capability_id = "seed-%s-%s" % (prefix, method)` from a family prefix, then looks it up in `seeds.SEED_CAPABILITIES` | the closed-repertoire convention B3 opened; it still runs, but it can only ever mint the `seed-`-prefixed ids that made the repertoire closed |

The first is a **dangling reader**: a name that no longer exists. The second is
a **naming-architecture** staleness: the generator is intact and produces
exactly what it always did, but that output describes a world where a `seed-`
prefix was the only admissible capability id, which is no longer the world.

**These outputs remain valid history.** Each archive is a true measurement of
its own tip, and nothing in this batch claims otherwise. B3 did not rewrite
these reports; it rewrote the two live B8 tests that asserted the closure,
because those tests gate live behaviour rather than record it. The distinction
is the whole point: an archived generator records, a live gate decides.

No note was added beside the generators. Both directories are archived evidence
trees, and adding a file to them would be the first step toward editing them.
This section is the record.

### One cross-lane consequence of closing FA-01, recorded not repaired

`tests/test_inv_b14_retention.py:420` pins `reports/cap-sheets/b-live-cap.md`
**byte-for-byte** to its blob at `794520f`, on the reasoning that B14 needs a
new freeze and the parent sheet must not drift. Correcting FA-01 necessarily
changes those bytes, so the pin now fails.

The pin's *purpose* still holds. Its two substantive assertions are in a
different test and both still pass on the corrected sheet: `` `B14` and `B15`
are **not allocated `` and "They need a new freeze of this sheet". B14's own
freeze is untouched, and nothing in its evidence moved.

`tests/test_inv_b14_retention.py` is not in this lane's path ownership, and
rewriting another lane's gate to accommodate a coordinator correction is the
pattern `AGENTS.md` forbids. The conflict is recorded here for the lane that
owns the pin, with the narrow repair: the pin should compare the sheet's
**freeze-relevant** content — the route, the bounds, the dispatch caps, the
allocation totals and the B14/B15 non-allocation — rather than the whole file,
so a corrected count in a panel-summary sentence cannot re-break it. A
byte-identity pin over a document that a coordinator may correct is a pin over
the wrong thing.

### FA-05 — the documents that own current status do not record the batch

`AGENTS.md` names `reports/PROJECT-LEDGER.md` as owning current status and
`docs/design/REFINEMENT-ROADMAP.md` as owning stage status. **Neither
mentions this batch, its two live campaigns, or its two search passes.** The
ledger still opens with "Current checkpoint: 2026-09-30" and its Stage 9
dispositions are the pre-batch ones. A reader of the ledger cannot learn
from the ledger what this batch established.

The assignment says "Keep one current completion report with
requirement-to-evidence mapping". **There is no completion report for this
batch.** `reports/STAGE-09-CONSOLIDATION.md` is an older branch's handback
(`a32ee20`), and `reports/STAGE-09-COMPLETION-MATRIX.md` opens with an
explicit banner that it is historical and non-governing.

Tests:
`test_the_status_owning_documents_record_this_batch[reports/PROJECT-LEDGER.md]`,
`[…docs/design/REFINEMENT-ROADMAP.md]`.

### One prose discrepancy, not recorded as a defect

`experiments/ad01/twodomain.py:102` and
`tests/test_inv_c7_two_domain.py:16` both say the Boolean instrument
"publishes 120 tasks". The census at `twodomain.py:111` iterates
`boolean_rule.SPLITS` (3) × `range(24)` = **72**, and I counted 72 distinct
task payloads. The 120 is wrong and the two files agree with each other, so
it reads as a single propagated figure rather than a contradiction.

It does not change any measured claim: the cluster count is 1 across 72
tasks and would be 1 across 120, because every task comes from one class.
I have left it out of the test file because the number is prose and the
measurement it supports is unaffected. Named here so the next lane does not
re-derive it.

---

## Contradictions between a document and the evidence

1. **`reports/workstreams/b13b-replseed.md:123` vs the census artifact.**
   One powered panel; three are. See FA-01.
2. **`reports/cap-sheets/b-live-cap.md:48` vs `census.json`.** Same error,
   in the document that gates live dispatch.
3. **`reports/PLAN.md` vs `git log`.** Six lanes `running`, ten `queued`,
   twenty-six landed. See FA-03.
4. **`reports/PLAN.md:61` vs the absent c4-live workstream.** Listed
   `queued, LIVE`; no report, no evidence, no test exists.
5. **`reports/PROJECT-LEDGER.md` and `docs/design/REFINEMENT-ROADMAP.md` vs
   the batch itself.** Both own current status per AGENTS.md and both
   describe the 2026-09-30 checkpoint. See FA-05.
6. **`tests/test_inv_b4_constant_score.py:313` vs the filesystem.** The test
   names a committed artifact that is not committed. See FA-02.

### Stale claims specifically asked about

- **Fixed-menu constructor.** `reports/PLAN.md:59` still describes lane C3
  as "replacing the two-member menu" as a pending task. The menu is gone.
  `reports/STAGE-09-COMPLETION-MATRIX.md` and `STAGE-09-RECOMMENDATION.md`
  both still argue from `_STRATEGY_SOURCE` having two members; the matrix
  opens with a banner declaring itself historical and non-governing, so I
  do not count those as live contradictions. The PLAN line is live.
- **Closed repertoire.** **No stale claim survives.** B3 opened the
  repertoire and, correctly, rewrote the two B8 tests that asserted the
  closure rather than deleting them; both now assert both halves (authored
  seeds alone still closed, which is what the archives measured). The four
  archived reports that read `repertoire_closed: true` are named in
  `RETENTION_BLOCKER["archived_in"]` as true measurements of the world at
  `35ba5e9`. I verified `default_repertoire()` and single-argument
  `eligible_for` are unchanged and the panel power census did not move —
  consistent with B8's own distinction between panel power and the
  retention closure.
- **"Only powered panel".** Still false in two live files. See FA-01.

### Historical reports that describe their own revisions

`STAGE-09-COMPLETION-MATRIX.md`, `STAGE-09-RECOMMENDATION.md` and
`STAGE-09-CONSOLIDATION.md` all cite symbols this batch deleted. I am **not**
counting these as contradictions: each is either banner-marked historical or
explicitly describes its own source revision, which is what AGENTS.md
requires. No lane edited any of them, which is correct.

---

## Credential sweep

**Count: 0.**

I scanned all 136 files changed by this batch against seven
credential-shaped patterns: `sk-`, `sk-or-v1-`, `nvapi-`, `ghp_`, `Bearer`
with a 24+ char token, any assignment of a 24+ char literal to a
key/secret/password/token/credential-named variable, any DSN carrying an
inline password, and `SETTLEMENT_GATEWAY_KEY=` with a literal. **Zero hits.**

I then separately reviewed every secret-*name* mention in the changed files
and confirmed each is a name, not a value:
`experiments/ad01/invr1b12_swe_construction.py:1288-1313` reads
`CX_AGENT_API_KEY` from `~/.claude.json`, moves it into the process
environment, and prints **only the variable name and the value's length**.
`_wsl_password()` (`:1268`) shells out to read a disposable role password
and interpolates it into an in-memory DSN. Neither writes a value to any
file, and neither value appears in the diff or in any evidence artifact.

Unknown billing stayed unknown throughout. `billed` appears as `null` or
`"unknown"` in every case across the new evidence; no `"billed": 0` appears
anywhere. `_receipt_actual_cost` is `null` on all five B12 operations and on
every B11 rung including the five that succeeded. The lost 4096 rung records
`input_tokens: "unknown"` and `output_tokens: "unknown"`, not zeros.

---

## Failure modes checked

| Failure mode | Result |
|---|---|
| Skips reported as passes | **None.** `-rs` on every run, zero skips in all six. 29 new test files swept for skip/xfail machinery: zero occurrences. |
| Fixture bytes relabelled live | **Not found.** B12's store rows carry 5 operations, 5 receipts with distinct outcomes (`lost-response`, four `observed-provider-failure`), and reservations of 2700–2771 units against a 65352-authorized allocation. The B14 live members carry real `operation_id` and `receipt_identity` (`gw:ad01-r4acq-…`) and name `acquired_from_provider: true`. B14's one offline demonstration is **explicitly labelled** "OFFLINE DEMONSTRATION, NOT A LIVE ACQUISITION" with `acquired_from_provider: false`. |
| Unknown usage reported as zero | **Not found.** See the credential sweep above. `carried_in_true_exposure: ">= 5563"` and the ledger's "Null billing is not measured zero" both hold. |
| Sealed assessment reaching a prompt | **Guarded and tested.** `tests/test_inv_b12_swe_construction.py:390` scans every recorded prompt for every recorded sealed value, by value rather than by name, and `construction.json` carries `sealed_values_per_dev_instance`. The one repair prompt (`invr1b12_swe_construction.py:302`) carries only the loader's own refusal on the model's own bytes — development information about a candidate, which is what makes it a repair rather than a resample. |
| Countercheck whose baseline was already red | **Not found in milestone A.** I read the baselines in `test_inv_a_counterexamples.py` rather than the summary; four of the seven run a real green execution first. The report itself discloses the two limits honestly (case 1's refusal is "unknown operation" because no prepared route-B op was reachable; case 6 distinguishes a hang from a refusal via its baseline). |
| Counts summed across runs | **Not done.** Six runs reported separately above, none summed. |
| Sealed values in a prompt | See above. |
| Fixture on the coordinator host | None. Every run executed in WSL as `ubuntu`. |

---

## The two search passes, independently checked

Pass 1 (`p1-search.md`) found P1-01 (a lost hold on `investigations.in_flight`
across two connections) and recorded P1-02/03/04. Pass 2 (`p2-search.md`)
found three: the fourth writer of `in_flight`, the `AnnAssign`/`NamedExpr`
gap, and `take_correction` locking an absent row. I verified all three
fixes in source rather than trusting the report:

- `mission.py:422` and `:497` and `:543` all take `FOR UPDATE`; `_replace`
  is gone.
- `improve_channel._attempts_frozen_write` refuses all 19 binding forms I
  probed, including the four P1/P2 named and fifteen they did not.
- `authority.take_correction:547-554` inserts the zero row
  `ON CONFLICT DO NOTHING` **before** the `FOR UPDATE`, making the conflict
  itself the lock, with the reasoning in a comment.

The passes' own recomputations of my headline numbers 1 and 3 agree with
mine. The pattern both named — *a lock taken on a row the writer may not
have created yet, or a read and a write split across two connections* — is
the right generalisation and it produced four real fixes.

---

## What this batch did not establish

- No acquired program this batch produced.
- No learning advantage. No learned arm exists to compare.
- No transfer. The retained archive has zero usable members, and the
  two-domain crossing transfers a predicate, not competence.
- No autonomous selection. The C7 crossing order is scripted.
- No two-domain comparison. Powered on one side only; the Boolean side has
  one independent unit.
- No eligible revision and no revised descendants. `c4-live` never ran.
- No B4 crossover. The sweep was cancelled; the direction is unknown.
- No completion report, and no update to the two documents that own current
  status.

---

## Final live process count

**0.** No Monitor armed, no subagent spawned, one pytest process at a time,
no network, no live model call. The scratch probe I wrote for the freeze
check was deleted before commit; only `tests/test_final_accept_findings.py`
and this report are added.

`git diff --name-only 794737f HEAD -- reports/evidence/` is **empty**.

Reviewed tip `794737f`. All evidence touched by this batch is additive over
`70223fb`; no pre-existing evidence file was modified.
