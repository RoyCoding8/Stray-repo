# Milestone B decomposition, read-only investigation
Read-only. No file but this one was written, no live run, no external call. Every code claim
carries `file:line`; every historical observation carries its evidence directory. Where a
prior claim is superseded, I name both and say which holds.
## (a) WORLD/FIXTURE CENSUS
B requires two genuinely different task structures, function identification from
observations and software diagnosis and repair through interventions, reusing existing
worlds where they meet the requirement (`WORKER-PROMPT.md:76-80`), and forbids relabeling
reducers as new domains (`docs/design/ARCHITECTURE-SYNTHESIS-2026-09-22.md` §13).
**Structure 1 exists once, in the right shape.** The Boolean instrument is four input bits,
four output bits, a public affine class optionally XORed with one pairwise product,
deduplicated by 16-bit truth table, a hidden target of four functions, at most eight queries
(`experiments/ad01/boolean_rule.py:1-9`, `:23-28`). Views carry task identity, class
descriptor, observed pairs and remaining budget; target tables never enter them
(`boolean_rule.py:11-14`). This is the correct instrument for structure 1 and it has a real
sealed surface.
**The other two "worlds" are the same structure relabeled.** Reduction-panel tasks are
op-list or vertex-edge-list reductions
(`experiments/ad01/worlds/world-0/within/ad01-w0-within-sw-00.json`, keys `family, fault,
ops, seed, task_id, template, witness`; the graph sibling
`experiments/ad01/worlds/world-0/transfer/ad01-w0-transfer-gr-00.json` carries `edges,
family, seed, task_id, template, vertices`), the scorer is a reducer, and the benefit is
`normalized_reduction` (`experiments/ad01/s09_e2_scored.py:116`). The ordering world is a
third instance, and its own module says the representation is portable while the policy is
not (`experiments/ad01/s09_representation_matrix.py:352-358`). B already demotes ordering
and reduction to regression or transfer instruments (`WORKER-PROMPT.md:78-79`).
**Structure 2 exists once and is the only world with real interventions.**
`experiments/ad01/s09_swe_world.py` is instrument `software-fault-repair-v1` (`:24`),
publishing `ACTION_TARGETS` (`:143`), `CONSTRUCT_TARGETS = ("code.inspect", "code.localize",
"code.try")` (`:152`) and a policy view of `action_schema, entry, instrument, ...` (`:154`).
`SweSession` (`:225`) implements `run_public_test` (`:293`), `inspect` (`:308`), `localize`
(`:317`), `try_edit` (`:329`), `repair` (`:353`), `score` (`:391`), `apply_action` (`:420`),
`run_episode` (`:531`). It is the only instrument where a policy action changes program
state and a test re-runs.
**Dedup and template separation: clean on the SWE side, weak on the reducers.**
`DEV_PROGRAMS` is three templates, `HELDOUT_PROGRAMS` is six, disjoint
(`experiments/ad01/s09_swe_tasks.py:393-394`); structures are `counting`, `state_machine`,
`accumulator` (`:34`), roles `bound`, `guard`, `update`, `window` (`:35`);
`enumerate_instances` is templates times mechanisms of split (`:678`); `protected_verdict`
(`:667`) is the sealed leg. The ceiling run records 3 dev templates, 6 held-out templates, 5
held-out mechanisms, 15 held-out families, 30 held-out instances, 30 distinct faulty
programs (`reports/evidence/inv_r1_e1_swe_ceiling/matrix.json`, `support`). I deduped the
frozen reducer trees directly: `experiments/ad01/worlds` holds 54 tasks but 27 distinct
software bodies, 19 graph bodies and 10 distinct (template, fault) pairs; `worlds_exp` 54
tasks, 27 software, 16 graph, 10 pairs; `worlds_panel` 54 tasks, 24 software, 18 graph, 18
pairs. Duplication near 2 per family, which is why the software panels' attainable positive
delta is 0. The reviewer reached the same conclusion from the scoring side
(`reports/workstreams/w5-final-review.md:25`).
**Other world families exist but are not wired into B.**
`experiments/representation/fixtures/` carries `graphs/`, `software/`, `controls` plus a
digest manifest. `experiments/representation/acquire/` carries `atom_core.py`,
`gr_adapter.py`, `sw_adapter.py`, `live_campaign.py`, `retention.py`, `panel.py`,
`null_core.py`, a second acquisition surface AD01 does not use. `experiments/agenda01/`,
`experiments/coord02/` (30 corpus tasks plus `protected/reference/` pairs for six families)
and `experiments/team01/` (16 tasks) are others. Adopting any needs a fresh instrument
qualification, and `AGENTS.md` forbids a second investigation owner, so reusing AD01 is the
default.
**Verdict.** Structure 1 = the Boolean instrument, structure 2 = the SWE world. Both exist
and are frozen, and their action vocabularies differ. No new world is needed. What is
missing is the pairing. No run has put the experience contrast, the retention campaign or
the selection ladder on the SWE world. Everything downstream of (a) is measured on reducers.
## (b) REPRESENTATION MATRIX STATE
All three representations share one action vocabulary,
`probe/observe/construct/use/check/stop` (`experiments/ad01/policy_action.py:32`). Parity is
`s09_arm_parity.compare_arms`, which refuses a single arm, refuses two arms of one
representation kind, and returns `Incomparability` rather than a zero
(`experiments/ad01/s09_arm_parity.py:68`, `:95`, `:249-275`).
**On the Boolean world the three-representation matrix is real and passes.**
`build_registry` registers the three live executors, not test doubles, and raises if any is
refused (`experiments/ad01/s09_representation_matrix.py:271-297`); `run_matrix` pairs each
arm with a rotating partner because `compare_arms` refuses a lone arm (`:306-325`). Tests
assert the three real arm names, all three comparable, agreement `("ast","graph","step")`,
and that a broken graph reports its own reason rather than a zero
(`tests/test_s09_representation_matrix.py:39`, `:70`, `:91`, `:95-120`).
**On the SWE world it is one supported cell of three, and both refusals have concrete
witnesses.** `support()` returns `supported_representations: ["python-step"]`,
`missing_representations: ["typed-ast","action-graph"]`
(`experiments/ad01/s09_swe_experiment.py:1596-1597`); the archived run agrees
(`reports/evidence/inv_r1_e1_swe/matrix.json`;
`reports/evidence/inv_r1_e1_swe_ceiling/matrix.json`). `missing_cells()` names the typed
AST's refusal as no view field carrying the program under repair and no node building
replacement source text, and the graph's as `ordering_graph_policy._parse_action`
deep-copying the raw action node, so a graph reading a test name out of the view still has
to spell that name in the record while the value the evaluator just read is discarded
(`experiments/ad01/s09_swe_ast.py:303-335`). The archived text is per-lineage: for typed
AST, `validator refused code.repair: action 'use' is not available in the Boolean world` and
`node set refuses view.source: probe.name: unknown view field 'source'`; for the graph, `no
swe World value exists; the executor's vocabulary is per-World and a swe observation is
{test, expected, actual, kind}, naming none of the admitted paths ['earlier', 'left',
'right']` (`reports/evidence/inv_r1_e1_swe_ceiling/matrix.json`, `missing_cells`). These are
harness and view-field defects, not notation defects, so the disposition is to repair the
harness, which `WORKER-PROMPT.md:84-85` explicitly prefers over a new notation.
`path_fork()` names the fork (`experiments/ad01/s09_swe_experiment.py:1601`): `extra_in_swe`
is `entry, last_effect, max_budget, public_tests, source, structure, symptom` while the
harness requires `action_schema, hypothesis_class, instrument, max_queries, observed,
remaining, split, task_id` (same evidence file, `path_fork`). `expressivity()` declines to
claim the cells, labelling its bytes `ORIGIN = "fixture-stand-in"`
(`experiments/ad01/s09_swe_ast.py:43`, `:369-416`) with an `origin_reason` that no live
provider produced them.
**Four construction opportunities per supported cell: satisfied offline, never on a live
route.** `LINEAGES_PER_CELL = 4` (`experiments/ad01/s09_swe_experiment.py:96`) and the
archived run has 12 lineages, four per kind
(`reports/evidence/inv_r1_e1_swe_ceiling/matrix.json`, `lineages`). The four python-step
lineages ran 156 rows, 124 repaired and 32 unrepaired; the eight typed-AST and graph
lineages ran 156 rows each, all 156 `refused` (same file, `rows`). `run_matrix` records an
unbuilt lineage as a `refused` row rather than dropping it, so a vanishing lineage is
distinguishable from one that never ran (`s09_swe_experiment.py:1251-1270`). **Two
separately measured ceilings already exist, which is the headroom B asks for before a large
run.** `probe_reach` (`:1416`) measures budget truncation and reports rate 1.0 on both
splits, 9 of 9 dev and 30 of 30 held-out instances reaching the fault line at a derived
budget of 303 (same evidence file, `probe_budget_reach`); `search_span` (`:1473`) measures
generator expressiveness and finds only 4 of 9 dev instances generator-reachable (same file,
`search_span`).
**The archived construction record.** `reports/workstreams/s89-a2.md` records 10 attempts: 3
timeout-unknown-exposure, 3 output truncation all at exactly 2048 output tokens, 4 execution
failure with `NameError: name 'reduce_graph' is not defined`, and no candidate ever
executed. `reports/workstreams/s89-b2.md` is the post-fix rerun: 4 of 4 execute and
preserve, 2 tie the incumbent and 2 beat it on size, on already-seen dev tasks, so an
intervention diagnostic and not held-out transfer evidence.
**The one-prompt claim is superseded.** The completion matrix says `render_output_prompt` is
the only live acquisition prompt and that E1 has one constructible cell, not nine
(`reports/STAGE-09-COMPLETION-MATRIX.md` §3.1, §3.2, and `:353-354`).
`reports/workstreams/w5-final-review.md:235` corrects this and the correction holds: two
live prompts exist, `live_construct.render_output_prompt`
(`experiments/ad01/live_construct.py:100`) and `packet.render_construction_prompt`
(`experiments/ad01/packet.py:342`), and `candidate_shape` serves both `graph` and `software`
(`packet.py:263-276`). `ordering` and typed AST still have none, so cut the nine-cell
implication, but for the narrower correct reason that two of three representation families
have no acquisition prompt at all.
**Verdict.** Boolean world carries all three representations. SWE world carries one cell,
four lineages, 156 rows, two witnessed refusals, two measured ceilings. The matrix is not
frozen at B's standard because the SWE harness path is forked and unusable
(`path_fork.common_path_usable: false`).
## (c) EXPERIENCE-CONTRAST STATE
**The three arms and the size matching are built and audited.** `build_arms` constructs
relevant from `learner.relevant_experience` (`experiments/ad01/learner.py:312`), none from
`no_experience_experience` (`learner.py:324`), irrelevant from `irrelevant_control_for`
(`learner.py:498`); `ARMS = (relevant, none, irrelevant)`
(`experiments/ad01/e2_replication.py:73`). Irrelevant is re-measured at `CONTROL_MAX_QUERIES
= 6` and refitted (`experiments/ad01/e2_contrast_campaign.py:78`, `:356`, `:395`) against
relevant at `EVIDENCE_MAX_QUERIES = 3` (`:73`). Padding goes into a `padding`-style key
outside the five-key allowlist, so the size matcher counts it and no policy receives it
(`e2_contrast_campaign.py:405`, `:421`; allowlist `packet.project_observations`,
`experiments/ad01/packet.py:218`). `treatment_input_audit` derives prompt and view contents
from rendered bytes (`e2_contrast_campaign.py:570`), `_interfaces_equal` compares
`eligible_methods` and `remaining` (`:639`), `_opportunity_equal` compares observation
counts (`:652`). Archived, `interfaces_equal: true`, `opportunity_equal: true`, all three
arms with `eligible_methods = ["seed-sw-ddmin","seed-sw-greedy"]`, relevant and irrelevant
at 3 observations and 1774 prompt characters, none at 0
(`reports/evidence/invr1e2contrast/report.json`, `size_matching` and
`treatment_input_audit`).
**The result is a null, and the panel cannot produce a positive.** First run
`reports/evidence/invr1e2contrast/`: both contrasts n=1, delta 0; 9 acquired; 9 receipts, 8
success, 1 lost-response. Replication in a second namespace
`reports/evidence/invr1e2contrastr2/`: both contrasts n=3, delta **-0.090909**, deltas `[0,
0, -0.2727]`, 9 acquired. The ledger's reading is right that the positive side is
unreachable on this panel (`reports/PROJECT-LEDGER.md:34`). The census says why with no
model involved (`e2_contrast_campaign.py:668`): it enumerates the whole decision grid,
`(method_id, max_queries)` over two methods and six budgets, against the default decision
`seed-sw-ddmin@8`, and reports `max_attainable_positive_delta: 0` with
`max_attainable_negative_delta: 0.538462` (`reports/evidence/invr1e2contrast/report.json`,
`reachability_census`). At census scale, software-within attainable positive is 0 with 0
open rows, graph-within 0.263158 with 3 open rows, graph-transfer 0.285714 with 3 open rows
(`reports/evidence/invr1w2retention-census/report.json`). Statistical power is unreachable
too: the frozen panel offers two software (family, template) clusters, minimum two-sided
sign-sweep p 1/2, against a protocol naming alpha 1/20, so 6 clusters are required
(`reports/evidence/invr1e2contrast/report.json`, `sign_flip` and `census`;
`reports/evidence/invr1e2contrastr2/report.json` records `minimum_p: "1/4"`, `n_pairs: 3`,
`nonzero_pairs: 1`).
**The view is pinned, and the pinned view is narrower than the prompt.** `SEALED_LABELS =
{"hidden","evaluator"}` and `SEALED_KEYS` (`experiments/ad01/packet.py:40-42`),
`with_held_out_canary` (`:63`), `strip_task` (`:112`), `method_task_view` (`:121`),
`leaked_answers` (`:185`). The audit records the gap: the irrelevant arm's prompt names
`reason` while `reasons_delivered` is empty, and the projection drops `p`, `reason`,
`reduction` (`reports/evidence/invr1e2contrast/report.json`,
`treatment_input_audit.arms.irrelevant`).
**Constant preservation is correctly not a benefit metric.** `verdict` is `preserved` on
every cell of every enumerated grid (`experiments/ad01/w2_retention_campaign.py:202-213`);
measured in `reports/evidence/invr1e2contrast/report.json`, where every arm's
`distinct_verdicts` is `["preserved"]` and `verdict_is_constant: true`.
`normalized_reduction` is the readable leg (`s09_e2_scored.py:116`), and the archived note
calls `preserved` a fixpoint of two composed invariants rather than a policy property.
**Development-only selection and repair: partly satisfied.** The five authored qualification
policies hardcode a `seed-sw-` method and `score_response` refuses an action naming an
out-of-family method (`experiments/ad01/s09_e2_scored.py:317`;
`reports/evidence/invr1w2retention/report.json`, `qualification_gate`).
`render_construction_prompt` carries a `PRIOR FAILURE (repair it)` line (`packet.py:387`)
and a prior-observations line (`packet.py:380`), both from development data only. The gap is
that this channel is not the one the E1 route uses: `live_construct.render_output_prompt`
(`live_construct.py:100`) takes a `history` argument and is the only prompt that route
exercises. **Failed acquisition is not becoming an authored learned arm.** The archived E1
r2 baseline carries `origin: "authored-control"`, `model_calls: 0` and an explicit
`not_counted_as: a live lineage` (`reports/evidence/w1-e1-boolean-r2/campaign.json`,
`authored_baseline`). That is the correct handling.
**The historical E1 zero is dominated by transport loss, not the length cap.** Zero
constructions, the three responses that arrived fail at any length because the model
narrates instead of committing, and 9 of 12 records are lost sends
(`reports/evidence/w1-e1-boolean-r3/RESULTS.md`). The route probe localizes the 502 to
output budget: the same protocol prompt returns 200 at 16 and 256 tokens and 502 at the
protocol's own 2048, while a short prompt returns 200 at 2048, finding
`output-budget-causes-the-502` (`reports/evidence/w1-e1-boolean-r3/route-probe.json`). This
corrects `reports/workstreams/w5-final-review.md:151`, which is right that the earlier
route-availability diagnosis was overstated. Four `KeyError: 'task_id'` driver faults are on
the record too (`reports/evidence/w1-e1-boolean-r3/exposure.json`, `driver_faults`).
**Verdict.** Arms, size matching, interface matching, view pinning and the development-only
repair channel all exist and are audited. The contrast has run twice with a replication
namespace. The result is a null on a panel whose positive side is 0 by construction, at 2 of
the 6 clusters the protocol needs.
## (d) RETENTION/TRANSFER STATE
**The retention leg has no lever, and the tree says so in code.** `RETENTION_BLOCKER`
(`experiments/ad01/w2_retention_campaign.py:176-200`):
`assessment_profile.default_repertoire` returns four authored seed ids and
`e2_replication.eligible_for` (`e2_replication.py:382`) returns the two belonging to the
task's family. Both sets are closed, frozen and identical for every arm, so a method
acquired on one task can never enter another task's repertoire and no difference in
`method_id` can be a retention effect. Measured: `repertoire_closed: true`,
`distinct_eligible_sets` length 1, `every_arm_sees_the_same_eligible_methods: true`
(`reports/evidence/invr1w2retention/report.json`, `repertoire_closure`;
`measureability.retained_method_leg_measurable: false`). The test suite asserts the closure
rather than describing it (`tests/test_ad01_w2_retention.py:71-72`: `eligible_count == 2`,
`retained_method_nameable is False`), implemented as `len(eligible) > 2`
(`w2_retention_campaign.py:367`). The leg is unmeasurable on this instrument, not
undermeasured. What the campaign measures instead is the transfer-shaped leg, a policy shown
a retained method's prior observations against one shown none
(`w2_retention_campaign.py:189-195`).
**Reuse versus cold acquisition: measured as cost, and cost is caching.**
`reports/evidence/inv_r1_e2_retention/costs.json` records retained 16345 units against cold
19614, `units_per_dispatch: 3269`, `crossover_uses: 5`. The completion matrix reads it
correctly, a cost crossover is not transfer it is caching
(`reports/STAGE-09-COMPLETION-MATRIX.md:210`, counter-reading `:221`). Note the mechanism:
the retained arm has `construction_dispatches: 0` and `reacquires: false`, so the saving is
the absence of one construction, not any property of the reused bytes. **Acquired bytes into
a new process: proved for one SWE lineage set only.** `reports/workstreams/s89-b2.md`
records 4 of 4 candidates executing and preserving in the fixed current tree, on
already-seen dev tasks, explicitly not held-out transfer evidence. The ledger carries the
same limit, six live executable STEP candidates refused as unchanged reducer delegation
(`reports/PROJECT-LEDGER.md:37`).
**Adaptation to a held-out family: n=1 then n=0.** `adaptation_contrast`
(`w2_retention_campaign.py:797`) pairs by position within split and names dropped positions.
The first run pairs one position and reports `arm_deltas` 0.269231 for all three arms with
contrasts of 0 at n=1 (`reports/evidence/invr1w2retention/report.json`, `adaptation`). Its
own caveat is the honest one: the splits are disjoint template sets, so position is the only
correspondence the frozen world offers and a position pairs two different tasks. That is a
within-versus-held-out comparison of arm means, not a paired measurement of one task in two
domains. The replication is real and produced nothing usable.
`reports/evidence/invr1w2retentionr2/report.json` records `is_replication_of:
"invr1w2retention"`, `campaign_kind: "replication"`, id `s09iso-invr1w2retentionr2-w0`,
model `nvidia/nemotron-3-ultra-550b-a55b:free`, `adaptation.n_pairs: 0`, three
`dropped_positions`, empty `arm_deltas` for all three arms, `null_dispatches` length 12.
Under B's own wording (`WORKER-PROMPT.md:96`) an archive with no usable members is a
no-acquisition result, not transfer evidence. `BUDGET_SEARCH_RANGE = tuple(range(1, 17))`
(`w2_retention_campaign.py:164`) shows the budget was searched offline, so the zero is not a
budget artifact.
**The qualification gate decides which panel can run, and it is software-only.** All five
authored qualification policies hardcode a `seed-sw-` method and `score_response` refuses
out-of-family methods, so on a graph target every one is refused before it can act
(`reports/evidence/invr1w2retention/report.json`, `qualification_gate`: `measured: 9`,
`readable: 9`, `readable_families: ["software"]`). The two constraints leave exactly one
place to run, `software` over `transfer` (`w2_retention_campaign.py:76-110`), and that one
place is closed, positive attainable 0. A structural bind, not an unlucky panel. An
inherited census defect is recorded and deliberately not patched:
`reports/evidence/invr1w2retention-census/report.json` carries `inherited_census_defect`
with 3 disagreeing task ids out of 18 rows and states `e2_contrast_campaign` is frozen and
not edited, so this module computes its own default, and where they disagree the inherited
number is the larger.
**Verdict.** Retention is unmeasurable by construction, adaptation is n=1 then n=0, the
replication is a no-acquisition result, and reuse versus cold is a caching result on a cost
ledger. The leg needs an open repertoire before any of its numbers can move.
## (e) AUTONOMOUS SELECTION STATE
**What runs today is real selection.** `selection.run_investigations`
(`experiments/ad01/selection.py:1055`) loops: the policy proposes, the proposal must be
inside the offered portfolio, the agenda must afford it, allocation is charged, the
development episode runs, the agenda advances, the policy observes, and the loop stops when
the policy declines or nothing is affordable (`selection.py:1100-1127`). It records admitted
decisions rather than intent (`selection.py:1070`). **The frontier is narrow.**
`portfolio_for_world` returns a portfolio whose docstring states "No ordering, no priority,
no next action" (`selection.py:402-407`). `AgendaPolicy` hard-codes families
`("software","graph")` (`agenda_policy.py:105`) with `selection.METHODS` per family
(`agenda_policy.py:110`), observes only whether a candidate's development episode was
retained and how much envelope is left, and never a held-out score
(`agenda_policy.py:92-183`). Every method is an authored `seed-sw-` or `seed-gr-` id.
**The five-way choice is not represented.** B requires a choice among diagnostic,
construction, reuse, continuation and stop (`WORKER-PROMPT.md:100-101`). The loop chooses
only which (capability, depth) to charge next (`selection.py:1112-1125`). There is no
construct decision and no reuse decision in the loop; continuation exists only as
`stop_reason` (`:1099`, `:1103`, `:1107`, `:1110`). Reuse cannot be a decision at all,
because the repertoire is closed (section d). Two of five decisions exist.
**The control is competent, and its arithmetic was not.** `FixedPolicy`
(`agenda_policy.py:186-270`) is pre-committed; the fitted family is `fitted_fixed_rule`
(`:292`), `constant_rule_search` (`:382`), `control_competence` (`:455`), `fitted_control`
(`:510`). The review found the defect: `_score_constant_rules` returns a sum over worlds
(`agenda_policy.py:435-440`) while arm rows divide by `len(cells)`, so the E3 ratio is
exactly 3.0 at every non-zero budget, true but vacuous
(`reports/workstreams/w5-final-review.md:99`). The fitting searches method and depth on
development data, which is what `WORKER-PROMPT.md:101` asks for, so the control definition
is adequate and its scoring was not. **Arms and budgets.** `_arms` returns agenda plus the
pre-committed control and `_fitted_arms` adds the fitted control
(`experiments/ad01/s09_e3_selection.py:73`, `:93`); `BUDGETS = (8,14,20,30,40,60)` (`:54`),
`SATURATED_AT = 20` (`:61`). The archived crossover
(`reports/evidence/inv_r1_e3_selection/e3-crossover.json`) records the agenda ahead on
diagnoses at 14, 40, 60 and on held-out at 14, 60; the pre-committed control ahead on
held-out at 20, 40; the fitted control ahead nowhere
(`reports/evidence/inv_r1_e3_fitted_control/e3-fitted-control.json`:
`fitted_control_ahead_on_held_out_at: []`, `budgets_where_the_two_controls_disagree: [14]`).
**A store witness exists, and it is the strongest thing in this section.**
`reports/evidence/inv_r1_e3_selection/e3-store-witness.json` carries
`connected.admitted_decisions` with capability id, charge, dispatch state, operation id,
receipt identity, receipt outcome, settled flag and next decision per seq, the
decision-and-effect chain B wants. The ladder artifact
(`reports/evidence/inv_r1_e3_ladder/e3-postfix-ladder.json`) carries an authority block with
development and operation ceilings, a correction budget, a store fingerprint and a cap sheet
derived before any store effect. **Three of the four E3 directories are retracted and the
retractions bind.** `reports/evidence/inv_r1_e3_selection/RETRACTED.md` retracts every
result read off that JSON. `reports/evidence/inv_r1_e3_ladder/RETRACTED.md` is narrower:
`e3-postfix-ladder.json` is not retracted, but one key inside it is, and a reader cannot
tell that from the file; the sidecar is
`reports/evidence/inv_r1_e3_ladder/e3-postfix-ladder.supersession.json`.
`reports/evidence/inv_r1_e2_transfer/RETRACTED.md` retracts the mechanism claim that
experience steers the diagnostic the model proposes.
**The selection is on reducers.** The frontier is two families of reduction tasks, and
nothing in `selection.py` or `agenda_policy.py` names the SWE world, so B's structure-2
requirement is absent from the selection leg entirely. **A related verified mechanism
defect.** `rule_learner.VersionSpaceLearner.choose_query` reads only `len(queried)` and `x
not in queried` (`experiments/ad01/rule_learner.py:40-50`); the revision module names it as
its ceiling (`experiments/ad01/learner_revision.py:20-24`) and attributes the learner at
`:1097`; the reviewer verified it (`reports/workstreams/w5-final-review.md:207`). **Sealed
assessment forbids what a selection comparison needs.** `policy_assess._effect` refuses
`request_model` with "model execution is unavailable in sealed assessment"
(`experiments/ad01/policy_assess.py:252`), `_candidate_from_action` refuses a
policy-supplied `candidate` because a learning policy directs method execution and does not
answer the panel task itself (`policy_assess.py:200-210`), and `_run_arm` re-initialises
`state = {}` per task at `policy_assess.py:273`, the private-state-per-task defect the
ledger records under learner improvement (`reports/PROJECT-LEDGER.md:37`).
**Verdict.** A real run-time chooser, a real pre-committed and fitted control, a real store
witness, a real authority ledger. Two of the five required decisions exist, one is
structurally impossible, two are absent, and the whole comparison is on reduction tasks.
## (f) PROPOSED LANES
Sixteen lanes, disjoint paths and stores, TDD, serial coordinator integration.
**OFFLINE. No model call. These can start now.**
- **B1, repair the SWE harness fork, not the DSL.** Extend the view contract and action
  admission to the seven fields `path_fork` names
  (`experiments/ad01/s09_swe_experiment.py:1601`;
  `reports/evidence/inv_r1_e1_swe_ceiling/matrix.json`) so `compare_arms` is reachable on
  the SWE world. Acceptance is three comparable representation kinds, or a *new* refusal
  with a concrete witness. Do not add a notation.
- **B2, close the graph executor's view-read defect.** `ordering_graph_policy._parse_action`
  discards the value the evaluator read (`experiments/ad01/s09_swe_ast.py:303-335`). Offline
  proof on the Boolean world that a graph arm can act on an observed value rather than a
  literal.
- **B3, open the repertoire.** The one lane that unblocks (d) and (e). Give
  `assessment_profile.default_repertoire` and `e2_replication.eligible_for`
  (`e2_replication.py:382`) a path for a method acquired on a prior task to enter a later
  repertoire, with a reducer whose verdict can vary (`w2_retention_campaign.py:176-200`).
  Offline first: a fixture showing a retained method nameable in a second task's
  `eligible_methods`. The closure assertion at `tests/test_ad01_w2_retention.py:71-72` must
  be changed by an accompanying change, never weakened in place.
- **B4, fix `_score_constant_rules`** to return the mean, not the sum
  (`experiments/ad01/agenda_policy.py:435-440`), and re-derive the crossover offline as a
  new freeze. Do not overwrite the archived numbers. The old 3.0 is not a retraction of the
  direction.
- **B5, fix per-task state in sealed assessment.** Carry policy state across tasks within an
  arm at `experiments/ad01/policy_assess.py:273`, with a clean-baseline counterexample where
  cross-task state changes the decision.
- **B6, fix the query-selection ceiling.** `rule_learner.choose_query` must respond to a
  revision in the query policy (`experiments/ad01/rule_learner.py:40-50`). Offline fixture
  where a revised selector changes which query it asks first.
- **B7, add the two missing decisions as policy surface.** Extend
  `selection.run_investigations` (`selection.py:1100-1127`) so a proposal can name
  construct, reuse or continue, and prove offline that all three are refused today. B3 is a
  prerequisite, so reuse stays refused until it lands.
- **B8, power the panel.** The frozen software panel has 2 clusters against 6 required
  (`reports/evidence/invr1e2contrast/report.json`, `sign_flip`) and software-within
  attainable positive is 0 (`reports/evidence/invr1w2retention-census/report.json`).
  Enumerate the templates and mechanisms reaching 6 clusters with a non-zero positive
  ceiling, and report it as a census.
- **B9, add an acquisition prompt for `ordering` and typed AST, or record `remove`.** Cut
  the nine-cell reporting surface to the cells that exist
  (`reports/STAGE-09-COMPLETION-MATRIX.md:353-354`). Two of three representation families
  have no acquisition prompt, so the honest disposition is delete the table, not build two
  prompts to fill it.
- **B10, write the B cap sheet from the complete matrix before effects.** The two live
  campaigns carry schema, namespace, freeze digest, matrix and per-request units
  (`reports/evidence/invr1e2contrast/report.json`, `cap_sheet`: 18 construction dispatches,
  19 physical sends, 2492 units per request, 2048 max output tokens, 300000 ms deadline).
  B's matrix is larger and needs its own. `reports/cap-sheets/` holds four files and none is
  a B sheet.
**LIVE. These need the verified free route and must wait for route verification.**
The route is reachable and unpinnable at once: the frozen model id is absent from the live
catalog of 256 models, dispatching it anyway returns 200 naming that exact id, and the same
id has a second spelling (`reports/evidence/w1-e1-boolean-r3/route-probe.json`, finding
`frozen-model-absent-from-catalog`). A freeze cannot pin the route, and a run is not
reproducible across a catalog change.
- **B11, route re-probe before any B dispatch.** The 502 tracks the requested output budget,
  not the prompt: 200 at 16 and 256 tokens, 502 at the protocol's own 2048, while a short
  prompt returns 200 at 2048 (same file, `output-budget-causes-the-502`). Every campaign
  currently caps `max_output_tokens: 2048` (`reports/evidence/invr1e2contrast/report.json`,
  `cap_sheet.bounds`). B must first establish a budget this route serves, and a changed
  budget is a new freeze that makes older and newer runs non-comparable
  (`WORKER-PROMPT.md:38-40`).
- **B12, the SWE matrix live construction run, 4 lineages per supported cell.**
  `LINEAGES_PER_CELL = 4` exists (`experiments/ad01/s09_swe_experiment.py:96`) and headroom
  is already qualified offline at rate 1.0 reach, 4 of 9 generator-reachable
  (`reports/evidence/inv_r1_e1_swe_ceiling/matrix.json`). Gate on B1 and B11. A failed
  acquisition stays a no-acquisition row and must not be replaced by an authored arm, which
  is what `reports/evidence/w1-e1-boolean-r2/campaign.json` does correctly with
  `not_counted_as: a live lineage`.
- **B13, the E2 contrast replication on the SWE world or on a powered panel.** Depends on B8
  and on a positive ceiling that is not 0. Both existing namespaces
  (`reports/evidence/invr1e2contrast/`, `reports/evidence/invr1e2contrastr2/`) are reducers;
  a third run on the same closed panel is a pointless spend. Hold until B8.
- **B14, retention and adaptation, only after B3.** Gate on an open repertoire. Without B3
  this is a third no-acquisition result (`reports/evidence/invr1w2retentionr2/report.json`,
  `n_pairs: 0`).
- **B15, the selection comparison on both structures, only after B7.** Requires the
  construct, reuse and continue decisions to exist. The fitted control is already the right
  shape (`agenda_policy.py:510`); the frontier is the missing half.
- **B16, follow acquired bytes into a new process.** One lineage set has run in the fixed
  tree on already-seen dev tasks (`reports/workstreams/s89-b2.md`). A new process and a
  held-out family are unproved, and the held-out SWE families are 6 templates over 5
  mechanisms (`reports/evidence/inv_r1_e1_swe_ceiling/matrix.json`, `support`).
**Sequencing.** B1, B3, B4, B5, B6, B8 start immediately and need nothing. B2 and B9 follow
B1. B10 gates every live lane. B11 completes before B12, B13, B14, B15 or B16 dispatch
anything. B12, B14 and B15 are the three lanes that actually close the B comparison, and B3
decides whether B14 can close at all.
## Biggest gap
**The retained-method leg has no lever, and that removes one of the five autonomous
decisions entirely.**
`RETENTION_BLOCKER` states it in code (`experiments/ad01/w2_retention_campaign.py:176-200`):
the repertoire is closed and identical for every arm, so a method acquired on one task can
never enter another task's repertoire, and no difference in `method_id` can be a retention
effect. Measured: `repertoire_closed: true`, `distinct_eligible_sets` length 1,
`retained_method_leg_measurable: false` (`reports/evidence/invr1w2retention/report.json`).
The ledger agrees, method identity is unmeasurable under the same authored repertoire
(`reports/PROJECT-LEDGER.md:35`).
B asks for retained reuse versus cold acquisition, for adaptation to a held-out family, and
for a program choosing among diagnostic, construction, **reuse**, continuation and stop
(`WORKER-PROMPT.md:94-101`). All three land on that hole. The replication confirms rather
than relieves it, `n_pairs: 0` and 12 null dispatches
(`reports/evidence/invr1w2retentionr2/report.json`). The qualification gate means the one
open-ceiling panel, graph, cannot be run on this instrument, while the runnable panel,
software, has maximum attainable positive delta 0
(`reports/evidence/invr1w2retention-census/report.json`).
Everything in (b), (c) and (e) can be advanced with work already scoped, and six lanes are
offline today. Retention cannot be advanced at all until the repertoire admits an acquired
method. That single repair unblocks the most, and it is bounded: open `eligible_for` to a
retained method, with a reducer whose verdict can vary, then rerun in a fresh namespace.
