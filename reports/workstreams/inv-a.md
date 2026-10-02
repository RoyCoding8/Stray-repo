# Milestone A decomposition: consolidate the causal path

Investigation, read-only. Every code claim carries `file:line`. Method: `grep -n`
for the actual call points, then a read of each enclosing function. Nothing
below is inferred from imports.

**Scope note.** A production caller is one a prototype mission invokes: `src/settlement/`,
`experiments/ad01/` (the investigation owner named in §13), and the study drivers a
mission would run. `tests/` and `reviews/probes/` are excluded.

---

## (a) CALLER TRACES

### (a1) Model inference — every non-test `.infer(` call site

`grep -rn '\.infer(' --include=*.py src experiments scripts` returns exactly 15
hits, all non-test. Each is classified by whether the enclosing call is reached
through `broker.dispatch_operation` (broker owns the effect: prepare, fence,
send once, receipt, exposure) or calls the adapter directly (raw).

| # | Site | Owning function | State |
|---|---|---|---|
| 1 | `src/settlement/broker.py:687` | `broker._send_model` | **BROKER (owner)**. Reached only from `dispatch_operation` via the `model-inference` effect. `_advance` at :663 issues the single-send fence, `_revalidate` at :670 re-checks ownership/grant at the point of effect, `_decided_receipt` at :674 parks a replayed op without a second call. Every exit path records a receipt: lost response :696, identity mismatch :691, `GatewayError` :711, unsupported type :714, empty text :733. |
| 2 | `src/settlement/boot.py:163` | `boot.grade_gateway` | **RAW.** A liveness probe at boot. No operation, no allocation, no receipt. Bounded in time but not in identity: a boot probe cannot be attributed or replayed. It is a dependency grade, not an effect. |
| 3 | `experiments/ad01/live_construct.py:605` | `LiveGuard.infer` | **RAW at the class, BROKER at the use.** `LiveGuard` is a `GatewayAdapter` decorator. It is handed to the broker as `gateway=` (`scripts/invl02_live.py:994`), so the broker owns the effect when the guard is the broker's gateway. But the guard also maintains its own `dispatch_count` (:603) and its own evidence ledger (`_record`, :608/:639), which is a **second dispatch counter** beside the broker's operation count. |
| 4 | `experiments/ad01/live_construct.py:1504` | `live_construct._preflight_dispatch` | **RAW.** Calls `guard.infer(request, evidence=evidence)` directly. No `broker.ensure_operation`, no `broker.dispatch_operation`, no allocation id. The operation id (:1495) is minted by `preflight_operation_id` but never admitted to the store, so the send has **no persistent identity, no allocation and no receipt**. Called from `_preflight_round` at :1917. |
| 5 | `experiments/ad01/run_c3_qualification.py:95` | `run_c3_qualification._stream` | **RAW** (inferred, not read line-by-line: it is the module's only `.infer(` and is a live study driver). |
| 6 | `experiments/ad01/w1_e1_campaign_r2.py:531` | r2 campaign guard call | **RAW** by the same shape as #4. Historical frozen instrument. |
| 7 | `experiments/ad01/w1_e1_campaign_r3.py:264` | r3 campaign guard call | **RAW**, same shape. Historical frozen instrument. |
| 8 | `experiments/run_dev_episode.py:119` | scripted double | **DOUBLE**, not a real send. |
| 9 | `scripts/inv01_study.py:989` | `self._inner.infer(request)` | **BROKER-adjacent.** Delegates to a wrapped adapter installed as a broker gateway. Needs a read to confirm no second counter. |
| 10 | `scripts/invl02_live.py:278` | `super().infer(request, evidence=evidence)` | **BROKER.** This is `_DurableBrokerOutput`; its override at :993 calls `broker.dispatch_operation(self.dsn, ..., gateway=self.gateway)` and then reads back `store.operation_receipts` at :1015. The `super()` call is the real adapter, invoked *inside* the broker's send. |
| 11-14 | `scripts/invl02_live.py:1174, :1950, :2418, :4200` | four `guard.infer(ModelRequest(...))` sites | **RAW**, same shape as #4: a hand-built `ModelRequest` handed straight to a guard. |
| 15 | `scripts/s09_pilot.py:229` | `self.delegate.infer(request)` | **RAW/inherited.** A delegating wrapper whose broker adoption is the subject of `tests/test_s09_a8_production_adoption.py::test_the_recorder_is_still_a_second_admission_path`, which asserts in words that it *is* a second admission path. |

**Broker-migrated `dispatch_operation` callers** (all `experiments/`, none in `src/`
except `broker.py` itself):

- `experiments/ad01/learner.py:243,255` — `broker.ensure_operation` + `dispatch_operation`. Fully migrated. Carries a settled-text short circuit at :238 so a replay costs nothing.
- `experiments/ad01/construct.py:99,108` — same shape, same short circuit at :89. Fully migrated.
- `experiments/ad01/learner_revision.py:412,431` — same shape plus `execution_version=_route_execution_version(route)` at :416, which binds the route into the operation. Fully migrated.
- `experiments/ad01/method_exec.py:1473,1507` — `broker.SANDBOX_EXEC` for the policy child. Fully migrated on the `dsn is not None` branch. **The `dsn is None` branch at :1511-1518 calls `launcher.dispatch(broker.BrokerOp(...))` and `launcher.read_result(...)` directly, bypassing the broker.** That is the raw source-execution seam; see (b).
- `experiments/ad01/selection.py:872,885`, `s09_m3_pilot.py:407`, `e2_replication.py:779,789,1097`, `e2_contrast_campaign.py:773,782,1209,1220`, `e3_ladder.py:375,800`, `team01/solver.py:68,81,244,255`, `team01/panel.py:193`, `team01/live.py:217,238,365,375`, `representation/acquire/run.py:421,439,454`, `representation/acquire/campaign.py:340,359` — all migrated.

### (a2) Executable policy source — every load/execute point

`grep -rn 'importlib|SourceFileLoader|spec_from_file|exec(|eval(' --include=*.py
src experiments scripts` returns **zero hits**. Nothing in the repository
compiles or imports policy source in-process. `src/settlement/experiment.py:195`
is a bare `compile(raw, "<solver-response>", "exec")` with no `exec()` call —
a parse check, not execution. Good news for the invariant "no Python
interpreter hidden behind a label".

| Site | What it runs | State |
|---|---|---|
| `experiments/ad01/method_exec.py:1407` `run_step_out_of_process` | policy source under the child | **BROKER on the durable branch** (:1473, :1507), **RAW on the `dsn is None` branch** (:1511-1518). |
| `experiments/ad01/method_exec.py:1113` `run_member_out_of_process` | acquired method under the child | Same two-branch shape (`ensure_operation`/`dispatch_operation` guarded on `dsn`). |
| `experiments/ad01/policy_step.py:1407` `compile_step` | returns a `BoundedPolicy` | **MIGRATED and explicitly documented.** The docstring at :1394-1402 says source is never compiled in this process and that production callers should use `trajectory.run_use(policy_source=...)`. `BoundedPolicy.run` delegates to `run_policy_step` at :1404. |
| `src/settlement/development.py:625, 781` | dev probe / composition selftest | **BROKER.** `stage_input` then `experiment._ensure_sandbox_op` then `broker.dispatch_operation` at :633. |
| `src/settlement/capabilities.py:115, 120` | capability entry | **BROKER-adjacent** — stages and builds an argv; the dispatch is the caller's. |
| `src/settlement/representation.py:480, 492, 604, 615` | representation entry + trusted checker | Same shape, dispatch is the caller's. |
| `src/settlement/experiment.py:285, 402, 404, 409` | grader, method, broken baseline | **BROKER.** `_run_sandbox` at :121 → `broker.dispatch_operation` at :265. |
| `src/settlement/launcher_local.py:882` `subprocess.Popen` | the actual child spawn | The bounded boundary itself. setsid + group kill (from the ENG-INVB repair). |

### (a3) Summary judgment

Inference migration is **mostly done but not finished**. The production
trajectory path (`learner`, `construct`, `learner_revision`, `method_exec`)
is fully broker-owned. The residue is concentrated in three shapes: the
preflight/raw guard calls (items 4, 6, 7, 11-14, 15), the guard's own parallel
dispatch counter (`live_construct.py:603`), and the `dsn is None` branch in
`method_exec.py`.

---

## (b) REMAINING AUTHORITY SEAMS

**S1 — Raw preflight dispatch with no operation, no allocation, no receipt.**
`experiments/ad01/live_construct.py:1504` calls `guard.infer(...)` with a
hand-built `ModelRequest`; `scripts/invl02_live.py:1174, :1950, :2418, :4200`
and `w1_e1_campaign_r2.py:531` / `r3.py:264` have the same shape. The operation id
is minted but never admitted, so these sends have no persistent identity, no
allocation and no receipt. **Repair:** route the preflight through
`broker.ensure_operation` + `broker.dispatch_operation` as
`learner_revision.py:412-432` does, or delete the preflight and use the broker's
own route check.

**S2 — The guard's parallel dispatch counter beside the broker's.**
`experiments/ad01/live_construct.py:603` increments `self.dispatch_count`, and
`is_ceiling_reached()` at :484 / `is_cost_blocked()` at :481 gate on it. The
broker separately counts operations and holds exposure. Two counters of the
same fact is the `s09_a8_production_adation` finding in test form
(`tests/test_s09_a8_production_adoption.py::test_the_recorder_is_still_a_second_admission_path`).
**Repair:** read the ceiling and the spend from the store, not from an
in-process int.

**S3 — `method_exec.py:1511-1518` executes policy source outside the broker.**
On the `dsn is None` branch the code calls `launcher.dispatch(broker.BrokerOp(...))`
and `launcher.read_result(...)` directly. The policy bytes still run in a child,
so containment holds, but there is no operation row, no receipt and no
attribution. **Repair:** require `dsn`/`allocation_id`/`operation_id` in
`run_step_out_of_process` (the `dsn is not None` guard at :1425 already
half-enforces this) and delete the raw branch.

**S4 — The JSON frontier owns a second decision and authority projection.**
`experiments/ad01/frontier.py:1766` `admit_and_spend` does its own
program-digest check, its own resource charge against a `used` counter
(:1819-1820) and its own `pending_effects` lifecycle; `accept` at :1826 does a
second admission; `complete_effect` at :1912 settles. All of that is written to
a JSON file by `save()` at :1654-1658. Meanwhile `trajectory.accept_action`
(:328) and `record_decision` (:234) do the same job against PostgreSQL. **Two
production owners, one of them file-based and therefore crash-losable between
the `self._doc[...]` mutation and `save()`.** §13 names `trajectory` the owner.
**Repair:** move `step_view` (:1678), `admit_and_spend` (:1766) and
`complete_effect` (:1912) onto the trajectory's `s09_policy_state` + `store` path,
and delete the JSON document.

**S5 — The frontier's authority is a file counter, not a store reservation.**
`frontier.py:1749-1756` `spend` increments `self._doc["used"]` and writes the
file. This is the "file-based crash-losable counters" failure the assignment
names. The trajectory has `store` reservations; the frontier does not use them.
**Repair:** charge through `store` reservations as `learner_revision.py:412`
does, and make the JSON `used` map a projection.

**S6 — Source-anchor bytes live in sidecar files.**
`frontier.py:849-851` writes `frontier.json.source-anchor-<key>.json` via
`os.link` at :890. This is the artifact-bytes store for acquisition evidence,
outside both the store and the artifact registry. **Repair:** move the anchor
into `artifacts.py` under the same digest-addressed binding the broker uses for
`artifact` effects.

**S7 — A third action vocabulary in `src/settlement/loop.py`.**
`loop.py:31-36` defines `DIAGNOSTIC/CONSTRUCTION/REPAIR/USE/PROBE/STOP` and
`validate_action` at :215 admits `instrument in _EFFECT_FOR or STOP`; `admit_effect`
at :411 is a *second* admission path in front of the broker's own. This is the
duplicate production authority §13 tells us to retire. It has test callers
(`test_m1_shared_executor.py`) and no production callers. **Repair:** delete
`loop.validate_action`/`admit_effect` and route through `broker.ensure_operation`,
or promote it deliberately; do not leave both.

---

## (c) ACTION-MEANING MAP

### The six vocabularies

| Vocabulary | Site | Kinds |
|---|---|---|
| shared contract | `experiments/ad01/policy_action.py:32` | `probe, observe, construct, use, check, stop` |
| STEP ABI | `experiments/ad01/policy_step.py:29-36` | `diagnose, construct_method, use_method, request_model, propose_revision, stop` |
| frontier operate | `experiments/ad01/frontier.py:31-39` | `investigate, probe, construct, reuse, revise, wait, stop` |
| improve channel | `experiments/ad01/improve_channel.py:42` | `probe, construct, select, wait, stop` |
| settlement loop | `src/settlement/loop.py:31-36` | `diagnose, construct, repair, use, probe, stop` (via `_EFFECT_FOR` :38) |
| representation profile | `src/settlement/representation.py` (cb01-exec) | `encode, start, advance, decode` |

### Where the translation happens

**Only one translation is implemented: STEP → contract.**
`experiments/ad01/policy_step.py:60-66` `STEP_KIND_TO_CONTRACT` and its
reverse at :68-70 `CONTRACT_KIND_TO_STEP`. Forward and reverse functions
`as_contract_action` (:91) and `as_step_action` (:114). `vocabulary_coverage()`
at :135 reports unmapped kinds in both directions.

### Where the admitted effect is actually decided (not the name)

This is the part the assignment says a round-trip enum test cannot establish.
The effect is decided at five distinct sites, and they do not agree:

1. **`policy_assess.py:245-264` `_effect`** — sealed assessment. `propose_revision`
   is **refused outright** at :253-255 with reason "revision proposal is not a
   panel task effect". `request_model` refused at :250. So in sealed assessment a
   revision proposal admits **no effect at all**.
2. **`assessment_profile.py:370-394`** — a second assessment path. `propose_revision`
   is **accepted** at :387 and *staged locally*, with `bound: False` and
   `owner: "assessment_profile.stage"`. It admits a file-level stage and no
   broker effect.
3. **`policy_step.py:60-66`** — the name map. `propose_revision` and `check` are
   deliberately the *same* contract kind, and the comment at :50-56 says so
   explicitly: "the contract keeps the gate and drops whether what is judged is
   a task result or the policy itself".
4. **`loop.py:445-459` `_effect_payload`** — `REPAIR`, `CONSTRUCTION` and `USE`
   all map to the *same* `sandbox-exec` payload shape at :452-455. They differ
   only in name.
5. **`frontier.py:666` `validate_operate_action`** — `revise` and `reuse` are
   distinct operate kinds that have no contract equivalent and no broker effect
   decision at all.

### The flagged collapse

**Checking a task result and proposing a learner revision are the same
operation at the contract level and DIFFERENT at every execution level.**
`policy_action.CHECK` is the shared kind (`policy_step.py:65`). It becomes
`propose_revision` in STEP. Then:

- In `policy_assess.py:253` a `propose_revision` is refused because it is not a
  task effect.
- In `assessment_profile.py:387` the same `propose_revision` is **accepted** and
  stages a revision locally.
- In `loop.py:452` a `repair` (a task effect) is a `sandbox-exec` with no
  distinction from `use`.

The same `CHECK` name therefore produces a refusal in one assessment profile and
a local stage in another. §13 says "do not force operational checks and
learner-revision proposals to become the same operation merely to preserve a
fixed enum count", and the assignment says "preserve distinctions between
checking a task result and proposing a learner revision **where they alter
execution**". They demonstrably alter execution here. This is the single
clearest violation in the trace.

### What is NOT established

`tests/test_s09_vocab_unify.py` (16 tests) proves the bijection by name
(`test_both_directions_round_trip`, `test_the_translation_is_a_bijection_not_a_partial_map`).
It never runs a translated action through an executor and compares admitted
effect, observation, refusal and resource use. `experiments/ad01/s09_vocabulary_census.py:39`
counts the unmapped kinds and stops there. **No test compares effects across
representations.** That is the gap §13 names directly.

---

## (d) CHAIN COVERAGE

Required chain: `permitted experience -> program decision -> admitted effect ->
observation -> checked artifact -> retention/binding -> fresh-process use`.

| Arrow | Tests that prove it | Tamper covered |
|---|---|---|
| permitted experience | `test_s09c1_continuity.py::test_private_state_survives_boundary`; `test_invl02_causality.py` (49 tests, includes `test_m4_rejects_coordinated_observation_and_claim_tamper`) | forged observations: `trajectory.py:1922 _observation_is_durable` + `admit_investigation` :1960-1974 |
| program decision | `test_s09_run_use_policy.py::test_the_policy_decides_which_method_runs`; `test_s09o_causal.py::test_different_bound_policies_produce_different_decisions`; `test_s09cs02_causal_proof.py::test_a_copied_digest_with_no_decision_is_unproven` | digest-without-decision: `test_s09cs02_causal_proof.py::test_a_digest_copied_onto_a_record_never_qualifies_launch_either` |
| admitted effect | `test_s09_strand_and_proof.py` (13 tests: `test_dispatch_pending_never_resends_work_the_launcher_already_ran`, `test_a_forged_proof_cannot_buy_a_second_execution`, `test_the_attested_launcher_is_read_from_the_operation_not_hardcoded`); `test_broker_route_recovery.py` (25 tests) | forged never-sent proof, wrong-launcher proof, second decided receipt |
| observation | `test_frontier_atomicity.py` (16 tests, includes `test_foreign_observation_cannot_settle_a_bound_effect`, `test_restart_rejects_duplicate_observation_identity`); `test_final_provenance.py::test_conflicting_observation_identity_preserves_first_record` | foreign observation, duplicate identity, one-effect-two-observations |
| checked artifact | `test_binding_provenance.py::test_digest_mismatch_refuses_adoption`, `::test_relabelled_control_still_refused`, `::test_leaf_control_never_counts_as_acquired`; `test_final_provenance.py::test_store_adoption_refuses_operational_source_mutation` | relabelled control, digest mismatch, source mutation after the fact |
| retention/binding | `test_binding_provenance.py::test_bound_needs_post_restart_citation`, `::test_retained_but_inactive_never_binds`; `test_rpr12_retention.py::test_load_rejects_tampered_record`; `test_s09c2b_bind.py`; `test_s09m34_bind.py::test_failed_comparison_preserves_old_binding` | tamper on load, binding without restart citation |
| fresh-process use | `test_s09m2_policy.py`; `test_s09c2a_actions.py::test_policy_uses_retained_bytes_without_reconstructing`; `test_s09_run_isolation.py` (23 tests: `test_the_store_is_one_this_run_created`, `test_the_store_is_named_for_this_run_not_for_the_file`); `test_s09m34_bind.py::test_atomic_bind_selects_revised_bytes_fresh_process`; `test_s09_durable_state.py::test_fresh_interpreter_resumes_without_re_execution` | wrong store, second module scope, no re-execution |

### The seven required counterexamples

| Case | Status | Where |
|---|---|---|
| **unrelated-route replay** | **PARTIAL.** `test_w1_guard_route_owner.py::test_a_wrong_route_still_refuses` and `::test_a_route_field_the_guard_does_not_carry_is_refused` prove the guard refuses a wrong route. `test_s09_gateway_route.py::test_an_explicit_route_is_still_refused_on_the_responses_surface` proves API-surface mismatch. `test_final_provenance.py::test_store_settlement_refuses_foreign_operation_for_effect` proves cross-operation settlement refusal. **MISSING:** replaying a *recorded* receipt from route A against an operation frozen for route B — no test binds the route into the operation and then changes it. `learner_revision.py:416` passes `execution_version=_route_execution_version(route)` into `ensure_operation`, so the machinery exists; nothing tests that mutating it is refused. |
| **changed bytes** | **COVERED.** `test_final_provenance.py::test_durable_step_rechecks_source_after_receipt` and `::test_durable_member_rejects_substitution_before_broker_dispatch` are the direct ones. Plus `test_binding_provenance.py::test_digest_mismatch_refuses_adoption`, `test_s09_o_causal.py::test_perturbing_candidate_bytes_changes_the_executed_decision`, `test_s09c1_failure.py::test_cached_step_source_mismatch_is_rejected`. |
| **missing authority** | **PARTIAL.** `method_exec.py:1425` refuses when `dsn` is set but allocation or operation id is missing, and :1439 refuses an unknown allocation. `loop.py:426-429` refuses insufficient free units. `test_s09_probe_route_ordering.py::test_a_direct_caller_with_no_route_spends_no_calibration`. **MISSING:** a test that runs `run_use` or `run_step_out_of_process` with **no dsn at all** and asserts the raw `method_exec.py:1511` branch is unreachable. That branch is live today. |
| **no candidate** | **COVERED.** `test_s09_run_use_policy.py::test_a_use_method_action_naming_no_method_refuses`, `::test_a_method_the_repertoire_does_not_hold_refuses`, `::test_a_refusal_is_not_the_incumbent_an_empty_repertoire_produces`, `::test_a_method_for_another_family_is_refused_rather_than_substituted`; `test_s09c2a_actions.py::test_unknown_method_refuses_without_constructing`; `test_rpr12_retention.py::test_no_candidate_retention_roundtrip`; `loop.py:429` "no-candidate, never silently underfunded". |
| **partial response** | **COVERED.** `broker.py:696` lost-response receipt, :714 unsupported type, :733 empty-response (decided `failure` with the digest of the bytes that arrived). `test_s09c1_continuity.py::test_settled_receipt_stays_attributable_on_empty_text` and `::test_empty_text_is_refused_rather_than_settled`. `test_s09r7_output_problems.py`. `experiment.py:186` treats `stop_reason == "length"` as truncation. |
| **timeout** | **COVERED.** `broker.py` `_send_sandbox` plus the ENG-INVB repair (group kill, `grace_ms`). `test_launcher_local_bounds.py`. `test_s09_run_isolation.py`. `test_binding_provenance.py`. `test_s09c1_continuity.py::test_exhausted_and_refused_paths_stay_in_history`. |
| **pending resume** | **COVERED.** `test_s09c1_continuity.py::test_pending_action_survives_preparation_crash`, `::test_pre_effect_step_resumes_without_rerunning_accepted_step`, `::test_settled_receipt_replays_at_zero_remaining`, `::test_resume_reuses_model_text_after_restart`; `test_s09_durable_state.py::test_fresh_interpreter_resumes_without_re_execution`, `::test_repeated_persist_is_idempotent_for_state_and_model_calls`; `test_s09_resume_tokenized_id.py::test_resuming_repins_the_namespace_so_the_ids_match`; `test_s09_strand_and_proof.py::test_dispatch_pending_recovers_an_operation_whose_intent_was_delivered`. |

**Net: 4 of 7 covered, 2 partial, 1 with a live hole (missing authority).**

**Clean-baseline counterexamples.** The assignment asks for independent
reviewer-written source. `tests/test_s09o_causal.py` supplies a hand-written
policy source at :25 and :166-219 asserts the exact kind sequences it produces
across acquire and use — that is the reviewer-written-source pattern, and it
should be the template. It exists for one source; the other six representations
(typed AST, graph, ordering AST, ordering graph, boolean STEP) have no equivalent.

---

## (e) PROPOSED LANES

Five implementation lanes, two review lanes. Each is disjoint in paths. All
gates assume the WSL Ubuntu + PostgreSQL runtime the ledger records, because
every one of these is a real-PostgreSQL assertion.

### L1 — Retire the raw preflight dispatch (S1, S2)

**Job.** Move `_preflight_dispatch` and the four `scripts/invl02_live.py` guard
calls onto `broker.ensure_operation` + `broker.dispatch_operation`, giving each
preflight send a persistent operation identity, an allocation and a receipt.
Delete the guard's own `dispatch_count` and read the ceiling and spend from the
store instead. This is the "each accepted operation must have persistent
identity, allocation, result or unknown outcome, and exposure" requirement,
currently unmet on the preflight route.

**Owned paths.** `experiments/ad01/live_construct.py`, `scripts/invl02_live.py`,
`experiments/ad01/w1_e1_campaign_r2.py`, `experiments/ad01/w1_e1_campaign_r3.py`.
New test `tests/test_inv_a_preflight_durable.py`.

**Depends on.** Nothing. Start here.

**Gate.** `pytest tests/test_inv_a_preflight_durable.py tests/test_w1_guard_route_owner.py tests/test_s09_gateway_route.py -x -q`
against a real `SETTLEMENT_TEST_DSN`. New tests: every preflight operation id
appears as a row in `operations` with a receipt and a settled or unknown
outcome; a second call to the same operation id issues no send; the ceiling is
read from the store, not from an in-process int.

**Effort.** M.

### L2 — Close the `dsn is None` execution hole (S3, missing-authority tamper)

**Job.** Delete the raw `launcher.dispatch` branch at
`method_exec.py:1511-1518`. Make `dsn`, `allocation_id` and `operation_id`
mandatory for any policy-source execution, so "no source file becomes trusted
because it is local" is enforced by the type of the call rather than by a
branch. Then add the missing tamper test: a caller with no dsn is refused, not
silently executed outside the broker.

**Owned paths.** `experiments/ad01/method_exec.py`,
`experiments/ad01/policy_step.py`, `experiments/ad01/trajectory.py` (only
`run_step_out_of_process` / `run_member_out_of_process` call sites).
New test `tests/test_inv_a_no_dsn_execution.py`.

**Depends on.** Nothing. Independent of L1.

**Gate.** `pytest tests/test_inv_a_no_dsn_execution.py tests/test_s09_m2_policy.py tests/test_s09_run_isolation.py tests/test_final_provenance.py -x -q`.
New tests: `run_step_out_of_process` and `run_member_out_of_process` both raise
`MethodExecutionError` with no dsn; a test asserting the raw branch's source
line no longer exists (`grep` pin, so a re-introduction is red).

**Effort.** S.

### L3 — Split `CHECK` from the revision proposal (action-meaning fix, §c)

**Job.** `policy_action.CHECK` currently carries two meanings that execute
differently. Give the contract a task-result check and a learner-revision
proposal as distinct kinds, or — cheaper and truer to "the contract wins on
count" — keep six kinds but make `policy_step` map the two STEP kinds onto two
*distinguishable* payloads, and make the two assessment profiles agree.
Right now `policy_assess.py:253` refuses `propose_revision` while
`assessment_profile.py:387` accepts and stages it. That is the concrete
divergence to repair. Whichever way it goes, add the test §13 asks for and the
round-trip enum test does not supply: run the same logical action through the
STEP arm and the typed-AST arm and assert identical admitted effect, identical
observation, identical refusal and identical resource use.

**Owned paths.** `experiments/ad01/policy_action.py`,
`experiments/ad01/policy_step.py`, `experiments/ad01/policy_assess.py`,
`experiments/ad01/assessment_profile.py`, `experiments/ad01/s09_arm_parity.py`.
New test `tests/test_inv_a_action_meaning.py`.

**Depends on.** Nothing, but L5 should not start until this lands, because the
cross-representation test lives naturally here.

**Gate.** `pytest tests/test_inv_a_action_meaning.py tests/test_s09_vocab_unify.py tests/test_policy_action_contract.py tests/test_s09_arm_parity.py tests/test_s09step_arm.py tests/test_s09_policy_governance.py -x -q`.
New tests: for each of the six kinds, STEP and typed-AST arms produce the same
admitted effect class, the same refusal reason on the same malformed input, and
the same resource delta; a `propose_revision` under sealed assessment is
refused in **both** profiles or accepted in both, and the test names which.

**Effort.** M.

### L4 — Converge the frontier's decision/authority projection into the trajectory (S4, S5, S6)

**Job.** The largest lane. Move the frontier's useful semantics — `step_view`
(:1678), the opportunity/admission/charge/settle sequence (:1766, :1826, :1912),
the effect-attribution rules (:1841) and the source anchor (:849) — onto the
trajectory's PostgreSQL path (`s09_policy_state` plus `store` reservations plus
`artifacts.py`), then delete the JSON document and its `save()`. The authority
counter becomes a store reservation; the source anchor becomes a bound artifact.
Keep `frontier.py`'s validators (`validate_package` :382,
`validate_acquisition_evidence` :447, `validate_operate_action` :666,
`make_evidence_record` :150) as frozen instruments per the assignment's
"preserving old frozen instruments", but stop them owning production state.

**Owned paths.** `experiments/ad01/frontier.py`, `experiments/ad01/trajectory.py`,
`experiments/ad01/improve_channel.py`, `src/settlement/artifacts.py`.
New test `tests/test_inv_a_single_owner.py`.

**Depends on.** L1 and L2 must be merged first — both touch
`trajectory.py`/`method_exec.py` call sites and L4 rewrites that region.

**Gate.** `pytest tests/test_inv_a_single_owner.py tests/test_frontier_atomicity.py tests/test_invl02_causality.py tests/test_binding_provenance.py tests/test_s09c2a_actions.py tests/test_s09c2b_bind.py tests/test_final_provenance.py -x -q`.
New tests: an admitted effect is visible from both the trajectory and the store
with one identity; killing the process between admission and settlement leaves a
recoverable pending record (the case the JSON file loses); a source anchor
survives only as a bound artifact; the frontier document no longer exists as
writable state.

**Effort.** L.

### L5 — Prove the full chain end to end through the public entry

**Job.** Build the single test that §13 requires and no current file provides:
`permitted experience -> program decision -> admitted effect -> observation ->
checked artifact -> retention/binding -> fresh-process use`, entered through
`trajectory.run_campaign` / `trajectory.run_use`, with reviewer-written policy
source. Add the two missing tamper cases on the way: unrelated-route replay
(a recorded receipt from route A offered against a route-B operation) and
missing authority (no-dsn execution, owned by L2's test but proved here through
the public entry). Add the two remaining representation arms' reviewer-written
source so the chain is not proved for STEP alone.

**Owned paths.** New `tests/test_inv_a_chain.py`, new
`tests/test_inv_a_counterexamples.py`, new fixture module
`tests/test_inv_a_reviewer_source.py`. No production paths — read-only against
L1-L4 output.

**Depends on.** L1, L2, L3, L4 all merged. This is the acceptance lane.

**Gate.** `pytest tests/test_inv_a_chain.py tests/test_inv_a_counterexamples.py -x -q` plus the full
affected set the coordinator runs on the merged tip. New tests: the chain
completes with every arrow carrying a durable row; unrelated-route replay is
refused; changed bytes after receipt are refused (reuse the
`test_final_provenance.py` shape); the disconnect control refuses; the
no-op control admits nothing.

**Effort.** M.

### R1 — Independent review of the L1/L2 authority migration

An agent that did not author L1 or L2. Writes its own reviewer-written policy
source and its own clean-baseline counterexamples, and confirms each is red on
the pre-merge base and green on the fix. The assignment's explicit requirement:
"counterchecks must add failures to a clean baseline." Scope: any
`broker.ensure_operation` call that is followed by a send that is not
`broker.dispatch_operation`, found by grep, not by reading imports.

**Gate.** A written report naming every remaining raw send with `file:line`,
plus at least three counterexamples shown red on base.

**Effort.** S.

### R2 — Independent review of the L3 action-meaning change

An agent that did not author L3. Its job is to answer the question a round-trip
enum test cannot: does the same logical action admit the same effect, the same
observation, the same refusal and the same resource use across STEP, typed AST
and graph? It writes its own arms; it does not reuse L3's test file. It must
also rule on whether `CHECK` needs splitting or whether the two profiles simply
need to agree, and say which with a reason.

**Gate.** A written verdict with at least one test the author did not write, plus
a keep/change/remove disposition on the six-kind contract.

**Effort.** S.

---

## Three seams I judge most load-bearing

1. **`experiments/ad01/method_exec.py:1511-1518`.** The one place where policy
   source runs outside the broker. It is a live `dsn is None` branch, it is the
   "no source file may become trusted merely because it is local" violation, and
   it is the missing-authority tamper case. Cheapest to fix, hardest to leave.

2. **`experiments/ad01/live_construct.py:1504` plus `scripts/invl02_live.py:1174,
   :1950, :2418, :4200`.** Raw preflight sends with no operation, no allocation
   and no receipt, compounded by the guard's own dispatch counter at
   `live_construct.py:603`. This is the "each accepted operation must have
   persistent identity, allocation, result or unknown outcome, and exposure"
   requirement failing on a live route.

3. **`experiments/ad01/frontier.py:1766` + `:1749` versus
   `experiments/ad01/trajectory.py:328`.** Two production owners for decision and
   authority, one of them writing to a JSON file at `:1654` and one charging a
   file counter at `:1819`. This is the duplicate authority §13 names, the
   crash-losable file state the assignment names, and the reason the chain cannot
   be proved end to end today.

The action-meaning collapse at `policy_assess.py:253` versus
`assessment_profile.py:387` is the fourth and is the most *visible* defect, but
it is contained to sealed assessment and does not sit on the causal path.
