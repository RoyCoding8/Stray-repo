# Team 01 — implementation and live-test report (Cognitive Batch 02)

Branch `codex/implementation-cognitive-batch-02`, base `895afd3`
(`origin/codex/cognitive-design-02`). Design:
`docs/design/TEAM-01-IMPLEMENTATION.md`, semantics
`docs/design/TEMPORARY-TEAMS.md`. Plan mapping: `reports/PLAN.md`
(`87da009`). Representation live campaign is reported separately in
`reports/REPRESENTATION-LIVE3.md`.

Lane merges (all Nightjar, additive, serial integration by the coordinator):

| Lane | Merge | Content commits |
|---|---|---|
| T-RUNTIME (TM-01–04) | `efa4cf3` | `a5c4877` runtime+schema, `5dbb7f3` packet wiring, `7b456a7` single-shape path, `1da5748` reasoning_effort, `d680daf` refusal fix |
| T-WORLD (TM-05, oracle/TM-08) | `48bf3d2` | `06fbe76` frozen corpus + oracle |
| T-EXPERIMENT (TM-06–08) | `c1342c2` | `31f6747` doubled experiment layer |
| R-LIVE evidence curation | — | `3c3b0df` checker-clean live3 copy |
| T-LIVE (LIVE-03–07) | `12fa92d` | `f7cff5f` live planner + doubled tests |
| Integration fix | `f780228` | checkpoint manifest widened by migration 0014 (precedent `c8b24dc`) |

Shared contracts (coordinator-owned): `src/settlement/team.py` (team ABI),
`src/settlement/broker.py` (`reasoning_effort` validation + threading),
`src/settlement/gateway.py` (`ModelRequest.reasoning_effort`),
`src/settlement/gateway_http.py` (responses-API `reasoning.effort`,
fail-closed on other APIs), `src/settlement/context.py` (`team` packet kind,
team slots/resolvers, sandbox-exec team binding, resume `team` state),
`migrations/0014_team_runtime.sql`.

## 1. Requirement matrix

### TM rows (doubled gates on isolated real-PG databases)

| ID | Mechanism | Gate | Result |
|---|---|---|---|
| TM-01 | Bounded plans: `propose_team_plan` shapes, revision pinning | `tests/test_team_runtime.py` | pass (real PG) |
| TM-02 | Actual dispatch: `dispatch_child`, real broker operations | `tests/test_team_runtime.py` | pass |
| TM-03 | Owned submissions: `submit_child` digest binding | `tests/test_team_runtime.py` | pass |
| TM-04 | Integration/revision/resume: `assemble_and_join`, `revise_team_plan`, `resume_team` | `tests/test_team_runtime.py` | pass |
| TM-05 | Four-family tasks + protected checker + freeze/trace | `tests/test_team_world.py` | pass |
| TM-06 | Honest S/P/T panels via public entry `run_team_panel` | `tests/test_team_experiment.py` | pass |
| TM-07 | Template acquisition/transfer, visible status | `tests/test_team_experiment.py` | pass |
| TM-08 | Oracle/controls, incompatible-pair-then-fix proof | `test_team_world.py` + `test_team_experiment.py` | pass |

### LIVE rows (real gateway `muse-spark-1.3-contributor-free`, `/v1/responses`)

| ID | Work | Evidence | Disposition |
|---|---|---|---|
| LIVE-01 | Real broker/gateway inference + usage | `tlive*` planner ops with receipts; live3 12 calls 63498/42950 tokens | closed |
| LIVE-02 | Representation live path | `reports/REPRESENTATION-LIVE3.md`, `evidence-live3/` | closed, null result |
| LIVE-03 | Team dev with model planning + diagnostic + incompatible probes | 12 dev episodes (`dev-T-team01-{t01,t05,t09,t13}-r1-{diagnostic,incompatible,template-use}`), 9 ok / 3 fail | closed (hybrid campaign; retained as diagnostic in `evidence-hybrid/`) |
| LIVE-04 | Model-built template, dev-only selection, ≤1 frozen | `evidence/template-frozen.json` (`build-1-bind-first`, digest `4f5e7e79…b20ec`); attempt-1 voided under `voided-attempt-1/`; both model builds returned no text so selection fell back to dev ranking, reported as-is | closed (hybrid campaign; no-candidate path exercised honestly) |
| LIVE-05 | 48 S/P/T eval + 24 transfer episodes, live model work, rules recomputed | 84 episode records; checker clean, 0 problems; eval T 16/16 vs S 12/16 vs P 8/16; transfer cold_T 8/8, warm_T 8/8, S 6/8; pilot rules NOT promising (both) | closed, null result (hybrid campaign) |
| LIVE-06 | Fresh-process template load + resume after completed child | `evidence/continuity-probe.json`: success, `resumed` true, `resubmitted` [], join passed, protected 6/6, `simulated` false | closed (hybrid campaign) |
| LIVE-07 | Reconciliation of ops/receipts/usage/settlement/grants | `evidence/reconciliation.json`: grant-1 (86 ops, agreement true) + grant-2 (32 ops, agreement true), 0 missing, 0 without receipt, 0 unresolved; provider billing unknown (free tier), internal consumption fully counted | closed (hybrid campaign) |
| LIVE-03b | Live-solver dev calibration (S/P/T, model repair, no reference overlays) | `evidence-live2-panels/episodes/`: 12 dev cells (t01,t05,t09,t13 × S,P,T), 10 success / 2 failure (t09 S+T join-rejected at r1+r2 despite protected 6/6) | closed |
| LIVE-04b | Broker-routed model-built directive, ≤2 builds, ≤1 frozen | `evidence-live2-panels/builds/build-1.json` (model text from 9 dev records, directive 1386 chars, digest `e14149f5…`); warm-T trial success 6/6; `template-frozen-live2.json` → `live2-build-1`; one attempt used, no authored fallback | closed |
| LIVE-05b | 48 S/P/T eval + 24 warm/cold-T/S transfer, live model work, rules recomputed | 72 panel records; eval T 16/16 vs S 15/16 (+1 refused t06-S-r2) vs P 16/16 — beats-S false (tool ratio 1.47 > 1.25), beats-P true (level); transfer 8/8/8 — both beats false; neither panel promising | closed, null result |
| LIVE-06b | Suspend/resume continuity on the live path | continuity1 suspended t05 S; continuity2 resumed True, join True, protected 6/6; probe record in bundle | closed |
| LIVE-07b | Reconciliation + independent replay review of the live2 campaign | `reconciliation-live2.json`: 86 episodes, 85 agree, 0 missing receipts, 1 unresolved (t06-S-r2 refused cell, pre-fix 0/0 usage record retained as-run, receipts 890/563 present); `replay-live2.json`: 1 mismatch (same cell); `check-all-live2.json`: 86 records, controls pass, 7 quoted problems; provider billing unknown, internal consumption fully counted | closed |

Protocol ceilings honored (live2 campaign): 13 dev episodes (≤24),
1 template build (≤2), 1 frozen template (≤1), 48 eval (≤48), 24
transfer (≤24), 2 continuity probes (≤2). Campaign totals: 211 model
calls, 135 tool calls, 174881/255342 tokens. Full detail:
`reports/TEAM-01-LIVE2-PANELS.md`.

## 2. What the live run actually looked like

All 84 episodes ran the real team path (`propose_team_plan` ->
`dispatch_child` via the broker -> `submit_child` -> `assemble_and_join` ->
`freeze_candidate`, oracle-checked; 424 sandbox run envelopes with
`.gen/.spawns/.result.json` under `/tmp/asv2-live/team-live/runs/`).
Planner routing per episode: S=`forced-single`, P=`forced-alternatives`
(protocol-fixed, no model spend); every T-arm episode made one real
broker-routed model call. Of 44 T-arm calls, 18 returned usable plan text
(2791 in / 7616 out tokens) and 26 fell back to the cold policy with the
reason recorded (17 `fallback-empty-output`, 9 `fallback-gateway-error`;
0 timeouts, 0 auth/rate refusals). Fallback-heavy but honest: the empty-output
class is tested separately from timeouts (`test_team_live.py`), and the
gateway's empty responses are counted in the denominators, not hidden.

The `simulated: true` stamp on episode records is a panel-runner label for
protocol-fixed arms and reference-implementation child work; T-arm planning
conditioning is preserved byte-for-byte in each record's `live.calls` entry
(operation id, exposure, usage, outcome, text length) so actual conditioning
can be inspected.

## 3. Verdicts

- **(a) Mechanism, live: PASS.** The declared organization executed in 84/84
  valid episodes with bound receipts, integration checks and frozen
  candidates; fresh-process resume held with a single w2 submission and no
  duplicate successful effects. Model planner influence was partial
  (18/44 T calls shaped by live text).
- **(b) Team benefit, held-out: NULL.** Raw solves favor T (16/16 vs 12/16
  vs 8/16, no family lost), but the frozen `beats-S`/`beats-P` clauses fail
  solely on the resource ratio (T planner tokens vs forced zero-token
  comparators). No positive claimed.
- **(c) Retained coordination: NULL.** The frozen template bound in 8/8
  warm-T runs but changed 0/8 decisions (warm shapes equaled cold shapes);
  warm-vs-cold tied on solves at strictly fewer planner tokens, but the
  retention rule fails on the zero-comparator token ratio. Reported as-is.

## 4. Review passes (coordinator-executed, disjoint emphasis)

Both passes inspected the merged source (`895afd3..HEAD`) and executed
behavioral probes; solo execution is recorded honestly (not independent
reviewers).

- **Pass 1 — artifact/information/authority lineage.** Read the full
  shared-contract diff (`broker/context/gateway/gateway_http`,
  `acquire/{campaign,retention,run}`). Findings: none blocking.
  `bind_packet_invocation`'s `decision_kind` access matches the file's
  dict-row convention; `state["dsn"]` in team resolvers matches sibling
  resolvers (set at context build); `reasoning_effort` is fail-closed on
  non-responses APIs; invalid-procedure refusal carries the reason into
  arm-B `_refused_record` instead of raising.
- **Pass 2 — experimental validity, baselines, cost attribution.** Probes:
  (a) team checker on the live evidence root — clean, 84 records,
  oracle+barrier controls true, both pilot rules not promising with the
  cost-ratio clauses as the sole failures; (b) representation checker on
  `eval-live3` — clean, 48 records, promising false; (c) independent
  re-tally of episode/call/outcome/token counts from raw records, all
  matching `verdicts.json` (84 calls: 40 forced, 18 model-shape, 26
  fallback; 2791/7616 planner tokens). Finding: the `simulated` label on
  live episode records is misleading (panel-runner stamp; §2 explains the
  actual live content) — ledgered as a naming issue, not a validity
  defect, since conditioning bytes are preserved per record.
- **Integration regression:** the new `0014_team_runtime.sql` migration
  broke `test_checkpoint_writes_consistent_recovery_set`'s pinned manifest
  list; fixed per precedent `c8b24dc` (`f780228`), checkpoint/restore
  re-verified 14/14 on real PG.

## 5. Decisions and verification boundaries

- `HttpGatewayAdapter(endpoint=http://localhost:6446/v1, api=responses)`,
  `reasoning_effort=low` frozen into retention; per-worktree `PYTHONPATH`
  (stale editable `settlement` import caused one false failure, fixed by
  environment, not code).
- Actual evidence: doubled gates on isolated real-PG databases per lane;
  live gateway calls with receipts/usage; committed raw evidence sufficient
  to recompute (checkers + replay + freeze-check).
- Doubled (not live): S/P arm decisions, child worker implementations,
  oracle-adjacent unit paths. External: provider billing (free tier,
  unknown billing side; internal accounting complete).
- Full existing suite: see §7. Live gates `test_rpr13_endtoend.py` were run
  by R-LIVE (exit 0, live3 path) and excluded from the offline suite run.

## 6. Architecture-facing answer

- **Failed because of organization:** nothing structural — the team path
  (plan/dispatch/submit/join/freeze/resume) executed end-to-end live with
  balanced books. The `simulated` naming confusion is a labeling debt, not
  an organizational failure.
- **Depended on model/task difficulty:** most of the null. The free-tier
  model returned empty output on ~60% of planning calls; the frozen template
  never changed a decision because cold shapes already solved; reference
  workers cap observable team benefit by construction.
- **Actually persisted:** the team runtime + schema + packet wiring, the
  frozen template artifact, both checker-clean evidence roots, and the
  refusal/fallback accounting machinery.
- **Bottleneck justifying the first learner revision:** planner-call
  yield — a retry/negotiation policy for empty model output (currently one
  shot, then cold fallback) would raise the 18/44 shaping rate before any
  model or task change. That is an observed bottleneck, not a causal claim
  from any single agent's explanation.

## 7. Verification record and remaining dependencies

- Full suite on the merged tree (`f780228` + reports): **872 passed,
  0 failed** in 2133s on scratch DB `batch02_full` (real PG), excluding
  `tests/test_rpr13_endtoend.py` (live gates, run by R-LIVE: exit 0 on the
  live3 path). One integration failure was found and fixed in-sequence
  (checkpoint manifest vs migration 0014, §4); the 872-run covers the
  fixed tree including all `test_team_*` files.

Remaining: (1) provider-side billing evidence stays unavailable (free tier);
(2) runsc containment / PG-18 / deployment qualification remain separate
operational obligations, untouched by this batch; (3) `reviews/REQUEST.md`
update for the design role is committed alongside this report; roadmap stage
8.6 marked implemented-null (mechanism live, benefit unproven).
