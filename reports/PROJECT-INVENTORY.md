# Project inventory

Inspected 2026-09-30 at source tip `60964423455dcecb076745b3bcd85db0299dfbc5`. Three Luna reviewers independently covered runtime, cognitive call paths and committed campaign evidence. This report describes source presence and evidence separately. It does not report a full-suite, provider or deployment qualification performed by the researcher.

This is the baseline census. Later closure repairs, current stage status and the
next assignment are recorded in the [project ledger](PROJECT-LEDGER.md).

## Where we are

Stage 9 remains active. We have a substantial execution/investigation prototype and several learning experiment systems. Useful inherited competence, broad transfer, autonomous investigation selection and improvement of the learner remain unproven. Several narrow negative results are valid; they do not complete the broader comparison.

The intended architecture remains persistent investigations with versioned executable operational and improvement behavior over a trusted execution runtime. Model weights stay fixed. The system can potentially learn by changing executable methods, evidence selection, context, policies and acquisition procedures. A swarm is an allocation choice, not the owner of knowledge.

The most consequential implementation gap is fragmentation of the cognitive path. Development episodes, representation acquisition, AG01 agenda, Team01/Coord02 coordination and AD01 investigation have distinct controllers. They share execution infrastructure, but there is no demonstrated trajectory that connects memory, investigation choice, acquired methods, subsequent use and learner revision into one general learning cycle.

## Exact inventory

| Item | Count at inspected tip | Interpretation |
|---|---:|---|
| Tracked files | 3,250 | Includes evidence and documentation |
| Tracked bytes | 47,393,947 | About 45.2 MiB; excludes Git objects, environments and scratch |
| Runtime Python modules | 31 | 21,404 lines under src/settlement |
| Experiment Python files | 400 | 90,164 lines; not 400 capabilities |
| Test Python files | 417 | 332 active; 85 excluded under tests/_heavy_archived |
| Declared test functions | 4,341 | 3,470 active and 871 archived; not collected or executed case counts |
| SQL migrations | 18 | Last migration is 0018_receipt_provenance.sql |
| Major capability areas | 15 | Seven foundation areas and eight cognitive areas, defined below |

All 15 areas have code and identifiable call paths. That count is an inventory taxonomy, not a completion score, proof of intelligence or claim of unified integration.

## Seven foundation areas

| Area | Principal ownership | Built behavior and present limit |
|---|---|---|
| Durable effects and authority | store, db, authority, broker | Journal, outbox, reservations, receipt incorporation, grant/allocation ownership. Unknown effects remain explicit. Some declared ceilings require downstream enforcement. |
| Model gateway | gateway, gateway_http | Discovery/auth/inference separation, chat/responses decoding, route and usage handling. Current provider behavior and all protocol variants are not requalified here. |
| Bounded execution | child_limits, exec_profile, launcher_local, launcher_runsc | Child execution and local/gVisor profiles. The current Windows host cannot use the POSIX preexec path; real containment is still unqualified. |
| Artifacts and evidence | artifacts, evidence | Byte-addressed packages, retention, claims, warrants, opposition and invalidation. Evidence identity does not by itself establish semantic utility. |
| Capabilities, trials and release | capabilities, trials, evaluation | Candidate/trial/protocol/release machinery. Eligible learned releases must be demonstrated per campaign. |
| Recovery | broker, checkpoint/restore scripts | Pending effects, reconciliation, generations, barriers and restore fences. Database-backed and real failure interleavings were not re-exercised in this review. |
| Operator controls | api, templates, static assets | Authenticated durable-state views and pause/resume/cancel/quarantine/repair commands. They are controls over the prototype, not a complete autonomous product. |

The execution ownership is coherent: loop/run propose effect intents; broker admits and dispatches; the gateway or child launcher produces outcome evidence; store records identity and accounting. Artifacts own bytes; evidence owns claims/support. Cognitive policies do not own external authority.

## Eight cognitive areas

| Area | Principal path | What exists, and what is missing |
|---|---|---|
| Development episodes | settlement.development; experiments/run_dev_episode.py | Durable observe/propose/admit/diagnose/construct/check/select/bind lifecycle. It is separate from AD01's learner trajectory. |
| Memory and context | settlement.context/evidence; AD01 packet.py | Structured evidence and bound decision packets, beyond Markdown storage. AD01 has its own packet/experience path; learned retrieval or general memory benefit is unproven. |
| Agenda | settlement.agenda; agenda01 runner; AD01 agenda_policy | Durable agenda commands and bounded allocation policies. Current studies use supplied tasks and deterministic/authored policies. |
| Representation and transfer | settlement.representation; representation/acquire | Source/core/transfer packaging and retained-use instruments. Live acquisition across the planned representation/world matrix is absent. |
| Teams and coordination | settlement.team; team01/coord02 | Temporary plans, child construction/submission and join/rework paths. Coord02 carries executable decisions into real plan effects. These outputs are not inherited by a shared AD01 learner. |
| Persistent investigation | AD01 trajectory.py; settlement.loop | Durable investigation state, pending actions, observations, releases and subsequent use. The task stream is still supplied by campaign code. |
| Executable policies | AD01 policy_step/method_exec; STEP/AST/graph instruments | Candidate bytes can control actions through bounded executors. Representation qualification and learned policy acquisition are different evidence classes. |
| Learner revision | AD01 trajectory revision; learner_revision/improve_channel | Construction, freeze, assessment/bind machinery and a narrow live Boolean decision study. No eligible live revision or improved descendant cohort is demonstrated. |

Do not infer integration from an import list alone. The gap is semantic ownership and inheritance across these paths. Historical experiment controllers can remain as controls; production needs one defined investigation state, artifact contract and learning trajectory. Creating a third parallel lifecycle would make this worse.

For the original memory/dreaming/heartbeat idea, structured memory and executable retained artifacts are implemented. Agenda and repair wakeups also exist. A persistent self-directed background research and consolidation cycle has not been demonstrated. That remains a cognitive integration and evidence question.

## Current Stage 9 evidence

| Study | Raw observations | Defensible conclusion |
|---|---|---|
| E1 Boolean r2 | 8 attempts; 6 invalid-program responses and 2 transport losses; 0 usable programs | Route/contract behavior observed. No acquired program under that freeze. |
| E1 Boolean r3 | 8 planned opportunities; 12 records including retries; 0 usable programs; 4 task_id driver faults. Recorded spend 16 versus 12 derived record spends, with 4 carried-in dispatches | Separate carried exposure from current-round records and resolve the accounting/driver explanation. Zero artifacts is not a completed nine-cell comparison or a clean model-capability finding. |
| E1 representation/world matrix | Only Boolean output acquisition has a shipped E1 live construction entry. Other STEP/AST/graph/world cells are fixtures, unsupported or absent | The planned three-representation by three-world comparison remains incomplete. Other historical acquisition paths are separate experiments. |
| E2 experience contrast | 9 source-bearing parse-valid artifacts, 3 per arm. Relevant-minus-none and irrelevant-minus-none both average -0.090909 over 3 pairs. The panel's reachable positive delta is 0 | A scoped loss/null contrast on an uninformative positive side. It cannot establish whether useful experience helps on tasks where improvement is possible. |
| E2 retention/adaptation | Two namespaces, 54 recorded arm entries, 19/22 source-bearing parse-valid entries. Method identity sees the same two authored eligible methods. Usable adaptation positions n=1 then n=0 | Partial reuse/transfer evidence. Method-retention benefit is unmeasurable on this repertoire; adaptation and the full four-leg comparison are incomplete. |
| E3 fresh policy ladder | 36 offline cells, 6 budgets, 2 policies, 3 worlds. Authored agenda and precommitted schedules; no provider dispatch | A synthetic policy comparison. Changes in actions are real; autonomous formation of investigations is not demonstrated. |
| E4 revision attempt | 6 model-returned executable STEP candidates; 3 unique response digests; 0 eligible revisions, all refused as unchanged reducer delegation | Live executable-byte capture and scoped rejection observed. Revised descendants were unrun. Direct adapter calls do not supply shared broker reservation reconciliation. |
| Earlier method-wrapper campaign | 6 arm attempts, 3 model-acquired ddmin wrappers, 3 no-response arms. Three surviving paired deltas average -0.15277777777777776 | Wrapper acquisition exists. Utility was worse than control on those pairs; no general improvement or transfer claim follows. |

E1 r3's exposure disagreement is not automatically a cap breach: the artifact has both carried-in and current-round quantities. Preserve them and identify which count the guard applies. Raw route-probe findings also contradict their own response fields; use the raw measurements rather than the prose.

E3's latest fresh ladder has agenda/control means 0/0 at budget 8, 0.08372/0 at 14 and 20, 0.11175/0.11111 at 30, 0.14474/0.35928 at 40, and 0.20588/0.39101 at 60. These are scoped synthetic outcomes. The older default/fitted/oracle comparisons, sum/mean defect and superseded shared-instance tables must not be mixed into one headline.

E4's authored known-effect, no-op and disconnect controls qualify a narrow revision instrument. A known-effect fixture is not an acquired improver. Its 0.5017 blind-sequence headroom figure was withdrawn; the reported in-boundary range is 0.00622. A new descendant evidence-gathering experiment would need a new freeze and a precise claim about what changes.

Evidence pointers: reports/evidence/w1-e1-boolean-r2/, w1-e1-boolean-r3/, invr1e2contrastr2/, invr1w2retention/, invr1w2retentionr2/, inv_r1_e3_ladder/, inv_r1_e4/ and invl02_liveacq_r4/.

## The original twelve stages

| Stage | Current state |
|---|---|
| 1. Philosophy | Baseline selected; general discovery remains the goal |
| 2. Intuitive model | Baseline selected |
| 3. Formal description | Entities, contracts and limits specified; no proof of general intelligence |
| 4. Abstract architecture | Persistent investigation/executable behavior direction selected |
| 5. Representation and technology | Provisional choices implemented; empirical selection incomplete |
| 6. Practical specification | Foundation contracts specified |
| 7. Foundation prototype | Built; current deployment qualification partial |
| 8. Cognitive refinement prototypes | Closed at bounded mechanism scope; useful learning remains open |
| 9. Evidence-driven architecture consolidation | Active. Narrow studies have results; broad comparisons and integration claims remain open |
| 10. Complete system prototype | Not complete; isolated portions exist |
| 11. Operational qualification | Not complete; substantial groundwork exists |
| 12. Final implementation/release | Not started as a supported release milestone |

This is six specified design stages, two built prototype layers with scoped validation, one active consolidation stage and three incomplete downstream milestones. It is not an eight-out-of-twelve completion percentage: the stages have different sizes and can force revisions to earlier choices.

## Git and workspace map

The authoritative code snapshot is on codex/implementation-development-01 at 6096442, despite that branch's old name. The remote default still points at codex/architecture-handoff. A fresh clone must explicitly select the implementation branch; the default is not the current system.

| Git observation before this review | Count or finding |
|---|---|
| Persistent worktrees | 2: current implementation and old review-02 |
| Local branches | 49 |
| Remote branches | 147, all matching fetched tracking refs |
| Commits reachable from canonical tip | 119, including 12 after the DEV01 handback |
| Original retained history | rescue/debloat-work has 1,844 commits; old c06b3e9 remote has 1,752 |
| Current source content versus rescue snapshots | All four tree hashes equal c940572f5de07fcf492ad15512ee654937f3ec52 |
| Remote ancestry classification | 126 covered by pre-squash rescue; 2 by current ancestry; 19 separate histories |
| Local ancestry classification | 34 covered by pre-squash rescue; 4 other retained anchors; 1 current; 10 separate histories |

The squash preserved every tracked file at this checkpoint. Old branch tips becoming non-ancestors is expected after rewriting commit structure; it does not establish that their code is missing.

The full ref-to-commit census is in [branches.tsv](evidence/project-inventory-2026-09-30/branches.tsv) and [census.json](evidence/project-inventory-2026-09-30/census.json). These classify preservation, not semantic merge or inactivity.

Safe cleanup order: preserve/publish a full pre-squash archive anchor and this ref map; identify active owners; then retire covered task/review refs. Keep the current implementation, durable backup and genuinely separate useful changes. Do not merge every old branch or delete every non-ancestor. No existing local/remote branch was deleted in this review. The three isolated review worktrees and their temporary branches are removed after completion.

The unrelated D:/AI/Agent-Society checkout is an older, separate repository with 91 tracked files. It is not the current implementation. D:/AI/Agent-Society-v2-review-02 is an early review checkout with ignored caches/environment and a separate retained history. Neither was reset or deleted.

## Verification in this inventory

The runtime reviewer ran ten bounded gateway/profile/manifest/path/DB-URL test files at the inspected source: 95 passed, 4 failed, 13 skipped. All four failures were local-process profile cases on Windows rejecting preexec_fn. With S09ISO_DISABLE=1 and no test DSN, successful test bodies did not access PostgreSQL; an earlier setup attempt failed while connecting to the unavailable Linux socket. No PostgreSQL, DBOS, runsc or provider was qualified by those checks.

Reproduction in a disposable checkout:

```powershell
$env:PYTHONPATH=(Get-Location).Path
$env:S09ISO_DISABLE='1'
uv run --extra test pytest -q tests/test_gateway_boundary.py tests/test_gateway_free_signal.py tests/test_gateway_provider_field.py tests/test_gateway_usage_unknown.py tests/test_child_limits_platform.py tests/test_run_compose.py tests/test_posix_paths_checkpoint_restore.py tests/test_y1_database_url.py tests/test_s0_profile.py tests/test_s0_manifest.py
```

Declared test-function counts were obtained by AST parsing, without importing tests. Raw campaign fields and selected acquisition call paths were re-read by the researcher. No new inference, Jev call, database mutation or source repair was made. Archived tests were not rerun as a group.

After updating the ledger, the researcher ran its two affected offline audit suites with external DSN/gateway variables cleared: 49 passed in 7.90 seconds. Historical reservation audit content is unchanged. Current navigation links and diff whitespace checks passed; source, migrations, scripts, experiments and tests have no edits.

## Next decisions

1. Choose and specify one causal learning trajectory, including who owns investigation state, experience, retained behavior and future construction decisions. Reuse the durable runtime; retire redundant cognitive authorities only after their callers converge. This is a design decision before another implementation batch.
2. Choose informative task panels and competent controls with measurable headroom. Make actual artifact-producing preflight representative of the real prompt and budget. A larger swarm cannot repair an uninformative comparison.
3. Use that trajectory to acquire and reuse operational behavior across genuinely different task structures, then test one acquired improvement of its acquisition procedure on fresh descendants. Keep transport availability, executable acquisition, usefulness, transfer and improver benefit separate.

The most useful next work is a coherent theory/mechanism specification supported by these measurements. More generic audits, identical construction retries and conflicting status paragraphs would add little.
