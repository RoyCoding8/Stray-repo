# INV-C — Milestone C decomposition

Read-only investigation. Base `70223fb` on `codex/stage09-closure-checkpoint`.
Scope: WORKER-PROMPT.md:105-132, ARCHITECTURE-SYNTHESIS-2026-09-22.md §13, and
the four INV-C workstream notes. This note replaces an earlier design-only note
that occupied this path; no implementation is proposed here beyond the lane
boundaries in (e). Nothing below ran a live experiment, dispatched a child, or
called a model. Every number is read from a recorded artifact.

---

## (a) INHERITANCE CHANNEL STATE

**A.1 The designated owner does not own the improvement program.** §13 assigns
ownership explicitly: "Keep AD01's existing trajectory as the investigation
owner for this prototype. It owns accepted decisions, private-state
continuation, construction, retention and revision activation. `settlement`
owns external authority, operation identity, dispatch, receipts and accounting"
(ARCHITECTURE-SYNTHESIS-2026-09-22.md:249-253).

The two halves live in disjoint modules. `experiments/ad01/trajectory.py` imports
neither `frontier` nor `improve_channel` (import scan over all 2024 lines). The
improvement channel and its inheritance state live on the frontier JSON aggregate
`FrontierStore` (frontier.py:759) in namespace `invl02_m2` (frontier.py:25). The
trajectory's own durable decision state is Postgres `s09_policy_state`
(migrations/0017_s09_state.sql), written through `_s09_get` /
`_s09_insert_accepted` / `_s09_ensure_incorporated` (trajectory.py:261, :271,
:289), with accepted decisions at `record_decision` (trajectory.py:234) and effect
execution at `execute_pending` (trajectory.py:344).

So "the improvement program chooses it from permitted experience through the
same action executor" (WORKER-PROMPT.md:109) has no current executor to share.
`trajectory` reaches decisions through `agenda_policy.StepPolicyConsumer.decide`
(agenda_policy.py:958), which loads and persists policy state via
`policy_step.load_policy_state` (agenda_policy.py:984) and
`policy_step.persist_step_transition` (agenda_policy.py:1045-1162). The improve
path reaches its own executor at `run_operate_step` / `run_improve_step` /
`execute_operate_action` (improve_channel.py:1025, :1037, :1134). Two dispatch
stacks, neither of them `settlement`'s.

**A.2 Two "active program version" lineages already exist.** The frontier package lineage runs `adopt_revision` (frontier.py:2084-2138), version +1, immutable `op_source`, over JSON. The policy release lineage runs `selection.bind_revision` (selection.py:84) with `active_binding_for` (selection.py:54), over Postgres. `trajectory._construct_policy_revision` (trajectory.py:793-952) drives the second as `open_revision_proposal` → `construct.construct_policy` → `freeze_candidate` → `policy_assess` → `selection.bind_revision` (records.py:1387, :1437, selection.py:84); the frontier lineage runs through `improve_channel.admit_revision_under_freeze` (improve_channel.py:811). §13:334-348: "A static study driver with connected components is insufficient." Two version counters answering "which program is active" is the duplicate authority PROJECT-LEDGER.md:44 meant to close.

**A.3 The model constructor is a leaf effect, but it owns a fixed script.** The
requirement is exact: "The model constructor is a leaf effect, not the owner of a
fixed research script" (WORKER-PROMPT.md:110). Today the constructor is a leaf
*and* the script owner. `leaf_construct` (improve_channel.py:1196-1224) resolves
its emitted program by `imp_source = _STRATEGY_SOURCE[strategy]`
(improve_channel.py:136), a two-member dict `{"low": ..., "high": ...}`. Evidence
reachable by any revision is therefore a two-element tuple regardless of what
the revision decided: `_STRATEGY_EVIDENCE` (improve_channel.py:481) feeds
`REACHABLE_EVIDENCE` (improve_channel.py:489). The module states the consequence
itself at improve_channel.py:454-458: a descendant is not the reviser's evidence.
The decision can change probe allocation and pick between two constructions, but
cannot introduce a construction the menu lacks. That is the recorded cause of the
six-dispatch negative in (c).

**A.4 The declared freeze is not the enforced freeze.** `classify_revision`
(improve_channel.py:387-429) tests five conditions — emits a probe
(`_emits_probe` :239), x is data-dependent (`_x_is_data_dependent` :295), not the
incumbent choice (`_incumbent_choices` :318), not argmax of the frozen reducer
(`_reducer_argmax` :343, `delegates_to_frozen_reducer` :367) — but never "nothing
else changed". `FROZEN_FIELDS` (improve_channel.py:177) is declared;
`check_frozen` (learner_revision.py:282) applies to the *acquisition* revision,
not to the improve revision's emitted constructor source.

What actually protects the boundary is process isolation: the STEP child gets a
materialized view with no store or authority handle (`policy_step.materialize_view`
:256, `step_view` frontier.py:1678, state capped at `STATE_LIMIT_BYTES` = 4096,
policy_step.py:73), plus the `frozen_state` digest (improve_channel.py:436-443).
Over-spend is caught by `frontier._check_spend` / `spend` (frontier.py:1736,
:1749) — a grant control, not an interface control. The prior lane measured the
consequence: six variants changing probe allocation, construction, target, or step
skeleton each return `eligible` (reports/workstreams/w4-e4-interface.md §4). The
interface is not enforced against the thing it names.

**A.5 Pending work and restart.** `run.suspend_for_barrier`
(src/settlement/run.py:538) and `loop.resume_state` (src/settlement/loop.py:373)
are settlement-side. On the ad01 side `resume_campaign` (trajectory.py:1723-1748)
re-arms a campaign but is not a suspend primitive, and `FrontierStore` exposes no
suspend: its lifecycle surface is `round_command` / `spend_round_command`
(frontier.py:1593-1625), `ready_events` (:2040), `is_quiescent` (:2049). Restart
under a selected version exists as `adopt_revision` (frontier.py:2084-2138),
which resets private state, and `fresh_round` (improve_channel.py:1405-1420);
`test_m2_frontier_inherit.py` already asserts restart at store level. Neither is
reachable from `trajectory.run_campaign` (trajectory.py:1077).

**State.** Requirement 1 is partially built and structurally unreachable at the
executor level: the machinery exists in two disjoint subsystems, the constructor
menu is fixed at two members, and the declared freeze is advisory.

---

## (b) CONTROL QUALIFICATION STATE

**B.1 Four controls exist; the channel declares three.** Reviewer (effectful) at
`reviewer_revision` learner_revision.py:608, no-op at `no_op_revision` :628,
disconnect at `disconnect_revision` :655, disconnect-bytes at
`disconnect_bytes_revision` :710 with `DISCONNECT_X = 7` at :698.
`CONTROL_BUILDERS` registers all four (learner_revision.py:756-761);
`improve_channel.CONTROL_ROLES` declares three — `("known-effect", "no-op",
"disconnect")` (improve_channel.py:888) — and both `qualify_apparatus`
(improve_channel.py:891) and `make_control` (improve_channel.py:944) iterate that
tuple. One written control is unreachable through the channel's public control
entry. That is a registration defect, not a coverage deficit.

**B.2 The apparatus was qualified; the numbers are recorded.** `qualify`
(learner_revision.py:1121-1162) drove all four controls from identical starting
conditions. Recorded in reports/evidence/inv_r1_e4/result.json: known-effect
+0.2596, no-op exactly 0.0, disconnect exactly 0.0. "From identical starting
conditions, the first control must change an acquisition decision and the
disconnect must refuse" (WORKER-PROMPT.md:114-115) is met on the
acquisition-revision channel.

**B.3 Controls are not independently written against the inheritance channel.**
"independently written effectful, no-op and disconnect controls"
(WORKER-PROMPT.md:113). All four builders live in the same module as the
mechanism they test, and the improve-path entry `qualify_apparatus`
(improve_channel.py:891) builds its controls from the same `CONTROL_BUILDERS`
table. Reviewer separation (WORKER-PROMPT.md:141, :167) is not evidenced in the
control source.

**B.4 Restart-observation is built but never driven publicly.** `adopt_revision`
(frontier.py:2084-2138) + `fresh_round` (improve_channel.py:1405-1420) +
`descendant_of` (learner_revision.py:952) compose the mechanism for "Restart under
the selected version and observe its effect in the next descendant-producing
episode" (WORKER-PROMPT.md:116). `test_m2_frontier_inherit.py` (12 tests) asserts
restart at store level. No path from `trajectory.run_campaign`
(trajectory.py:1077) reaches them.

**B.5 Host blocker on every lane that runs a real child.**
`launcher_local.py:869-877` refuses `preexec_fn`, surfacing through
`method_exec.py:1466` as a lossy "child receipt identity is missing". That alone
fails 15 tests in `tests/test_s09_e4_qualification.py`. The ledger records the
constraint (PROJECT-LEDGER.md:38: "Windows cannot use the POSIX preexec profile")
and the assignment names WSL Ubuntu (WORKER-PROMPT.md:17-20). Any gate that spawns
children is a POSIX-only gate.

**State.** Controls exist, pass, and cover the required three roles, but they are
same-module, under-registered on the improve path, and unreachable from the public
entry. Restart is proven at store level only.

---

## (c) LIVE REVISION ATTEMPT STATE

**C.1 What the bounded attempt produced.** reports/evidence/inv_r1_e4/result.json,
`acquisition_summary`: `{"acquired": 6, "by_state": {"model-acquired": 6},
"dispatches": 6, "eligible": false, "verdict":
"no-eligible-revision-acquired"}`. Six live dispatches, all returning model bytes,
zero eligible. `ceiling`: best input 7, best mean 0.072, delta 0.00622, z 1.4187,
split `audit`, n_seeds 75. The `acquired` arm's recorded error is "no revision
bytes were acquired for this arm" with `x_probed: -1`. Freeze parameters:
`SPLIT="audit"`, `COHORT=range(150)`, `ACQUISITION_ATTEMPTS=6`
(learner_revision.py:1204-1206). Refusal diagnosis is instrumented:
`diagnose_refusal` (learner_revision.py:1219), `_adjudication` (:1263),
`INELIGIBLE_REPORTED` (:1216). The ledger agrees (PROJECT-LEDGER.md:37: "Six live
executable STEP candidates were refused as unchanged reducer delegation. No
eligible revision or revised-descendant cohort"), and the prior lane's verdict is
the right one — "a *completed negative* whose cause is a boundary that cannot
express the decision" (reports/workstreams/w4-e4-interface.md §5).

**C.2 Why the negative is not a learner-benefit result.** "Eligibility concerns a change to the acquisition procedure, not whether its score happens to improve" (WORKER-PROMPT.md:118-119; ARCHITECTURE-SYNTHESIS-2026-09-22.md:296-299). The measured spread makes that numeric. Channel headroom is 0.443 (`channel_headroom` :649); the reachable boundary range tops out at 0.00622 (`ceiling_over_inputs` :753, noise floor `noise_floor` :630). A 0.00622 range against 0.443 headroom cannot yield a benefit signal at any dispatch budget. The negative is a statement about the boundary's reachable range, not about whether a revised learner helps.

**C.3 The attempt is already bounded and honestly finishable.**
ACQUISITION_ATTEMPTS capped at 6, cohort frozen at 150 with a disjoint audit
split, terminal verdict recorded rather than retried. "If no eligible revision
exists, finish the bounded attempt honestly; do not run empty panels or claim a
negative learner-benefit comparison" (WORKER-PROMPT.md:123-124) is satisfiable
today with no new dispatches. The gap is not closure. It is that the attempt ran
against a boundary whose constructor menu could not express the decision (A.3), so
re-running it unchanged repeats a known outcome.

**C.4 The measurement milestone C asks for is not implemented.** "Compare revised
and parent learners on fresh acquisition episodes with matched opportunity and
complete resource accounting. Assess the descendants they produce on independent
tasks" (WORKER-PROMPT.md:120-122). The paired machinery exists — `paired`
(learner_revision.py:971), `compare` (:991), `evaluate_descendants`
(improve_channel.py:538), `lineage_descendant_score` (:571), `evaluate_lineage`
(:589), `descendant_delta` (:789) — but no caller combines revised-vs-parent on
fresh episodes, because there is no eligible revised arm. `live_attributable`
(learner_revision.py:1511) is the attribution seam that must survive the pair.

**State.** The bounded attempt is complete and honestly recorded. Requirement 3
cannot advance until the acquisition procedure can express a change, which is
requirement 1's work, not requirement 3's.

---

## (d) MISSION STATE

**D.1 There is no mission concept in either candidate owner.** "Build one
persistent mission entry with frontier, permitted experience, active program,
acquired artifacts, retained use and improvement mode" (WORKER-PROMPT.md:126-128).
A full scan of `src/settlement/*.py` returns zero occurrences of "mission" across
api, loop, run, agenda, agenda_policy, team, development, steward, experiment.
`api.py` contains no `experiments.ad01` import; three comments across the package
mention ad01 and nothing more.

**D.2 The closest durable aggregate is the wrong shape.**
`FrontierStore._blank_doc` (frontier.py:724-756) is the one durable record close
to a frontier: mission projection fields, environments, grant, used,
opportunities, observations, outcomes, obligations, pending_effects,
active_package, lineage, accepted_revisions, retained, evidence, private_state,
staged_candidate, round_results, round_journal, treatment_arms. Its mission
projection is checked by `_validate_document` (frontier.py:981) at :985-998. Three
disqualifying properties: it is Boolean-only, so not domain-general; it is not
the designated owner (§13:249-253 gives revision activation to the trajectory);
and it is a file-based aggregate, one of the named recurring failure modes,
"file-based crash-losable counters" (WORKER-PROMPT.md:150).

The trajectory's own durable state has the mirror problem. `s09_policy_state`
(migrations/0017_s09_state.sql) is per-investigation and per-seq, recording
`policy_input`, `policy_output`, `state_transition`, `effect_record`, and a
`status` CHECK constrained to `('accepted','incorporated')`. No row carries the six
mission fields as one entry.

**D.3 A second, competing decision-context owner exists.** `context.build_context` (src/settlement/context.py:36), `save_continuation` (:75) and `resume_package` (:155) assemble and persist durable decision context, including `pending_operations` and live attempts (context.py:188). A mission's permitted experience and pending work could live here, beside `FrontierStore.pending_effects`, beside `s09_policy_state`. "One persistent mission entry" is blocked by three candidate owners, not zero.

**D.4 Suspend/resume with pending work.** `run.suspend_for_barrier` (src/settlement/run.py:538) suspends settlement-side; `run.advance` (:242) and `run.check_eligibility` (:373) drive it; `loop.run_boundary` (src/settlement/loop.py:462) and `collect_wakeup_events` (:571) own the boundary. On the ad01 side there is no suspend. `resume_campaign` (trajectory.py:1723-1748) re-arms but does not restore a suspended in-flight operation with its old program and input identity, which WORKER-PROMPT.md:52-53 requires of pending work. The frontier store has the raw material — `pending_effects`, `ready_events` (frontier.py:2040), `is_quiescent` (:2049), and `adopt_revision`'s private-state reset (frontier.py:2084-2138) — but no suspend/resume pair over it.

**D.5 Two domains, one driver.** "a multi-episode mission across the two selected
domains" (WORKER-PROMPT.md:128-129). `trajectory._DIAGNOSTICS`
(trajectory.py:41) resolves exactly two families: `software` → `_resolve_sw`,
`graph` → `_resolve_gr`, with `_FAMILY_TAG` (trajectory.py:48), `_capability_for`
(:51), and `DEV_EPISODE_CAP = 3` (trajectory.py:398). So the trajectory can
traverse two families, but the SWE world cannot join the frontier channel.
`s09_arm_parity._WORLDS` (experiments/ad01/s09_arm_parity.py:30-65) maps
`{"boolean": "boolean_active", "ordering": "second_active", "swe":
"s09_swe_world"}` with the recorded reason that `swe` is "registered for
addressability, not because the harness can normalise its view" — the contract
view demands exactly eight public-state fields and SWE publishes twelve.
Milestone B names the two structures as "function identification from observations
and software diagnosis/repair through interventions" (WORKER-PROMPT.md:77-78), so
this view gap is on the critical path for B and C alike.

**D.6 Teams and background replay.** `team.propose_team_plan`
(src/settlement/team.py:496) and `resume_team` (:1228), `development.select`
(:982), `development.construct` (:700), `development.resume_episode` (:1044),
`experiment.run_abcs` (src/settlement/experiment.py:1099) with
`episode_cost_union` (:913) all exist. None is referenced by any mission entry,
because none exists. "add them only for a demonstrated dependency"
(WORKER-PROMPT.md:129-130) is satisfied by not scheduling them.

**State.** Requirement 4 has no owner today. The blocker is not missing code. It
is that three candidate aggregates each hold part of a mission, none holds all of
it, and §13 already names which should.

---

## (e) PROPOSED LANES

Twelve lanes in dependency order. Every gate is a pytest command plus named tests,
so an acceptance pass can run them without reading the lane. OFFLINE lanes run on
this host. LIVE lanes need the WSL Ubuntu profile (WORKER-PROMPT.md:17-20,
PROJECT-LEDGER.md:38), a verified free route, and a written grant and cap sheet
before any effect.

**Group 1 — one mission owner (prerequisite for everything else)**

**L1. Single durable mission entry.** Give the trajectory one record holding
frontier, permitted experience, active program, acquired artifacts, retained use
and improvement mode as one row, and retire the competing partial owners. Do not
add a table beside `s09_policy_state`; extend the migration that already owns
investigation state, then delete the frontier's `_blank_doc` mission projection
once callers migrate. Owns `migrations/0018_*.sql`, new
`experiments/ad01/mission.py`, `experiments/ad01/trajectory.py`,
`experiments/ad01/frontier.py`. Depends on nothing.
Gate `python -m pytest tests/test_mission_entry.py -q` —
`test_entry_carries_all_six_fields`, `test_entry_is_one_row_not_a_join`,
`test_frontier_mission_projection_deleted_after_migration`,
`test_s09_policy_state_has_no_competing_mission_columns`. Effort M. OFFLINE.

**L2. Suspend/resume with pending work.** Add suspend and resume to the mission
entry so an in-flight operation retains its old program and input identity across
restart, and route `settled.run.suspend_for_barrier` and `context.resume_package`
at the same record instead of a parallel continuation doc. Owns
`experiments/ad01/mission.py`, `experiments/ad01/trajectory.py`,
`src/settlement/context.py`. Depends on L1.
Gate `python -m pytest tests/test_mission_suspend_resume.py -q` —
`test_pending_retains_program_identity_across_restart`,
`test_resume_restores_pending_not_yet_effects`,
`test_continuation_doc_is_no_longer_the_resume_owner`. Effort M. OFFLINE.

**L3. Traverse two domains through one mission.** Close the SWE harness view gap
so a mission crosses function identification and software diagnosis, and prove it
across more than one episode. Owns `experiments/ad01/s09_arm_parity.py`,
`experiments/ad01/trajectory.py`, the mission view projection. Depends on L1, L2.
Gate `python -m pytest tests/test_mission_two_domain.py -q` —
`test_swe_world_view_normalises_to_eight_fields`,
`test_mission_crosses_both_domains_in_one_entry`,
`test_multi_episode_mission_advances_permitted_experience`. Effort L. OFFLINE.

**Group 2 — the inheritance channel**

**L4. Enforce the declared freeze.** Make `classify_revision` test "nothing else
changed" against `FROZEN_FIELDS`, so the six variants w4-e4-interface.md §4
measured as falsely `eligible` return ineligible. Replace the audit-script
measurement with a test. Owns `experiments/ad01/improve_channel.py`,
`tests/test_s09rev_boundary.py` (34 tests). Depends on L1, since the freeze belongs
on the mission entry rather than the JSON store. Gate `python -m pytest
tests/test_s09rev_boundary.py -q` —
`test_probe_allocation_change_is_not_eligible`,
`test_construction_change_is_not_eligible`,
`test_target_change_is_not_eligible`,
`test_step_skeleton_change_is_not_eligible`. Effort M. OFFLINE.

**L5. Independently written channel controls.** Move the three required controls
out of `learner_revision.py` into a reviewer-owned module, and reconcile
`CONTROL_ROLES` (improve_channel.py:888) with `CONTROL_BUILDERS`
(learner_revision.py:756-761) so no written control is unreachable. Owns new
`experiments/ad01/channel_controls.py`, `experiments/ad01/improve_channel.py`,
`tests/test_s09_e4_qualification.py` (15 tests, POSIX-only per B.5). Depends on L4.
Gate `python -m pytest tests/test_s09_e4_qualification.py -q` under WSL —
`test_effectful_control_changes_an_acquisition_decision`,
`test_noop_control_changes_nothing`, `test_disconnect_control_is_refused`,
`test_every_written_control_is_reachable_from_control_roles`. Effort S. OFFLINE
design, LIVE to qualify.

**L6. Restart under the selected version, observed in the next
descendant-producing episode.** Drive `adopt_revision` (frontier.py:2084) plus
`fresh_round` (improve_channel.py:1405) from `trajectory.run_campaign`
(trajectory.py:1077), and record the effect in the following episode's descendants
rather than in the restart's own receipt. Owns
`experiments/ad01/trajectory.py`, `experiments/ad01/mission.py`,
`tests/test_m2_frontier_inherit.py` (12 tests). Depends on L4, L5. Gate `python -m
pytest tests/test_m2_frontier_inherit.py -q` — `test_restart_adopts_selected_version`,
`test_next_descendant_episode_observes_the_change`,
`test_restart_alone_is_not_the_observation`. Effort L. OFFLINE with fixtures, LIVE
for the real child.

**L7. Widen the construction menu.** The lane that unblocks milestone C
requirement 3. Replace the two-member `_STRATEGY_SOURCE` selector
(improve_channel.py:136) with an inheritable procedure, so a revision's chosen
construction survives into the descendant as improve_channel.py:454-458 requires.
This is the earliest wrong boundary in milestone C: the constructor owns a fixed
research script. Owns `experiments/ad01/improve_channel.py`,
`experiments/ad01/construct.py` or its successor, `tests/test_s09_e4_channel.py`
(8 tests). Depends on L4. Gate `python -m pytest tests/test_s09_e4_channel.py -q` —
`test_revision_chosen_construction_reaches_the_descendant`,
`test_reachable_evidence_is_not_a_two_element_menu`,
`test_descendant_source_differs_from_parent_source`. Effort L. OFFLINE design, LIVE
to confirm a widened range.

**Group 3 — the live revision attempt**

**L8. Eligibility as procedure change, with the paired comparison.** Make
eligibility test a change to the acquisition procedure rather than a score delta,
and implement the revised-vs-parent fresh-episode comparison with matched
opportunity and complete resource accounting over independently assessed
descendants. Unreachable today because no eligible revision exists. Owns
`experiments/ad01/learner_revision.py`, `experiments/ad01/improve_channel.py`,
`tests/test_s09_learner_revision_accounting.py` (9 tests),
`tests/test_s09_e4_evidence.py` (8 tests). Depends on L7. Gate `python -m pytest
tests/test_s09_learner_revision_accounting.py tests/test_s09_e4_evidence.py -q` —
`test_eligibility_tests_procedure_change_not_score`,
`test_revised_and_parent_see_matched_opportunity`,
`test_descendants_assessed_on_independent_tasks`,
`test_reviser_own_score_is_not_the_measurement`. Effort L. LIVE. Needs a written
grant and cap sheet before any dispatch; `ACQUISITION_ATTEMPTS` stays bounded at 6
(learner_revision.py:1206).

**L9. Re-run the bounded attempt, or close it.** If L7 lifts the reachable range
above the noise floor (improve_channel.py:630), the attempt is re-run under a
*new* freeze, since a changed freeze does not make old and new comparable
(WORKER-PROMPT.md:39-40). If not, the existing negative at
reports/evidence/inv_r1_e4/result.json stands as the honest terminal record and no
empty panel runs. Owns reports/evidence/<new-freeze>/,
`experiments/ad01/learner_revision.py`. Depends on L8. Gate `python -m pytest
tests/test_s09_learner_revision.py -q` (16 tests) plus a recorded
`acquisition_summary` whose `eligible` flag is true, or an unchanged summary plus a
written statement that the bounded attempt is finished. Effort M. LIVE.

**Group 4 — boundary hygiene**

**L10. Retire the duplicate version lineage.** One answer to "which program is
active". Migrate the `selection.bind_revision` release binding and the
`FrontierStore.adopt_revision` version counter onto the mission entry, then delete
one of them; §13:334-348 forbids two. Owns `experiments/ad01/selection.py`,
`experiments/ad01/frontier.py`, `experiments/ad01/mission.py`,
`tests/test_ad01_menu_binding_gate.py`. Depends on L1, L6. Gate `python -m pytest
tests/test_ad01_menu_binding_gate.py -q` —
`test_single_active_program_version_authority`,
`test_method_release_and_policy_identity_remain_separate`. Effort M. OFFLINE.

**L11. One executor for the acquisition decision.** Route the improvement
program's choice through `agenda_policy.StepPolicyConsumer.decide`
(agenda_policy.py:958) and `policy_step.run_policy_step` (policy_step.py:457), so
trajectory and the improve path share one dispatch stack and one policy-state
record. Repair the boundary rather than adding a second executor. Owns
`experiments/ad01/trajectory.py`, `experiments/ad01/agenda_policy.py`,
`experiments/ad01/improve_channel.py`. Depends on L1, L4, L6. Gate `python -m
pytest tests/test_live_integration.py -q` (28 tests) —
`test_improvement_decision_runs_through_the_same_executor`,
`test_model_constructor_has_no_authority_over_grants`,
`test_model_constructor_cannot_edit_accounting_or_limits`,
`test_sealed_assessment_absent_from_the_prompt`. Effort L. OFFLINE with fixtures,
LIVE for real dispatch.

**L12. Independent acceptance.** A reviewer who authored none of L1-L11 runs the
full milestone C chain through the public entry and issues separate dispositions for
mechanism, acquisition, utility, transfer, autonomous selection and learner
improvement (WORKER-PROMPT.md:163-166). Owns `reports/` acceptance artifacts only.
Depends on all. Gate: the whole milestone C suite plus `python -m pytest tests/ -q -k
"mission or s09 or frontier or inheritance"`, every skip, failure and timeout
reported by scope, and no counts summed across runs. Effort M. OFFLINE.

**Not scheduled.** Teams (`team.propose_team_plan` src/settlement/team.py:496) and
background replay (`experiment.run_abcs` src/settlement/experiment.py:1099).
WORKER-PROMPT.md:129-130 adds them only for a demonstrated dependency, and L1 gives
the mission entry something they would have to share before any such dependency can
exist.

---

## Hardest piece to close honestly

Requirement 3, the live revision attempt. Not because the machinery is missing — `paired`, `compare`, `evaluate_descendants` and `descendant_delta` all exist — but because the measured boundary cannot express the decision being tested. Reachable range 0.00622 against channel headroom 0.443 (result.json ceiling; improve_channel.py:753, :649) means no dispatch budget produces a benefit signal, and `REACHABLE_EVIDENCE` (improve_channel.py:489) is a two-element tuple derived from a two-member source menu (improve_channel.py:136). The tempting failures are to widen the dispatch count, loosen `classify_revision` until the six already-measured variants pass (L4 surfaces them as ineligible), or re-report the completed negative as learner-benefit evidence. L7 is the only lane that changes the cause rather than the symptom, and L4's freeze has no meaning until L7 lands.

Sources beyond the inline citations: reports/STAGE-09-HANDOVER.md, reports/STAGE-09-CONNECTED-STATUS.md, reports/workstreams/dev02-ctx.md, dev02-ep.md, d02live-integration.md, and reports/workstreams/w4-e4-interface.md §4 (measured false-eligible variants), §5 (completed negative), §6 (host blocker).
