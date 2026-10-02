# Investigation Learning 02 coordinator plan

Base: beb4c29 on codex/stage-09-architecture-synthesis. Integration: codex/implementation-investigation-learning-02. Status observed 2026-09-23. Working tree clean at branch creation. Remote stage-09 tip equals beb4c29.

## Definition of done

M0 source map plus deterministic gates green on integration tip. M1 M4 deterministic paths verified without live spend. M5 live stays blocked without surviving grant. Completion matrix with exact commands and limits. Branch pushed with remote equality verified. Only owned disposable resources removed.

## Authority reconciliation observed

VERCEL_API_KEY present. AI_GATEWAY_API_KEY absent. S09_M5_LIVE_GRANT absent. S09_STUDY_CALLS_ALREADY_SPENT absent. SETTLEMENT_DSN absent. Historical spend 19 of 100 from reports/STAGE-09-COMPLETION.md worker-reported. Historical count is not proof of remaining calls. This message creates no new grant. No new inference without surviving grant verification.

## Task graph

| ID | Phase | Owner branch worktree | Owned paths | Depends | Checks | Status |
|---|---|---|---|---|---|---|
| M0 | failure boundary | wt/m0-baseline .worktrees/m0-baseline | reports/workstreams/inv-learning02-m0.md reports/evidence/s09-empty-receipts scripts/reconcile_empty_receipts.py src/settlement/broker gateway guard tests/test_m0_empty_receipts.py | none | scripts/s09_verify.py plus new regression plus nearby broker tests | merged d10c471 769d2f4 |
| M1 | shared executor | wt/m1-exec .worktrees/m1-exec | experiments/ad01/assessment_profile.py reports/workstreams/inv-learning02-m1.md tests/test_m1_shared_executor.py reports/jev/invl02-m1-*.json | M0 merged | same program matched effects dev versus assess | merged 99c4495 9fa550c 40 passed with M3 assess |
| M2 | durable frontier | wt/m2-frontier .worktrees/m2-frontier | experiments/ad01/frontier.py experiments/ad01/improve_channel.py reports/workstreams/inv-learning02-m2.md tests/test_m2_frontier_inherit.py | M0 merged M1 interfaces | restart plus second round via authored controls | merged 8148f6b 9d8e66f 12 lane 61 combined |
| M3 | rule instrument | wt/m3-rule .worktrees/m3-rule | experiments/ad01/boolean_rule.py experiments/ad01/rule_learner.py reports/workstreams/inv-learning02-m3.md tests/test_m3_rule_instrument.py | M0 merged | query limit plus private scoring | merged f0044b4 be09bd6 15 passed |
| M4 | offline compare | wt/m4-offline .worktrees/m4-offline | experiments/ad01/offline_recompute.py reports/evidence/invl02-e1e2 reports/workstreams/inv-learning02-m4.md tests/test_m4_offline_recompute.py reports/jev/invl02-m4-*.json | M0 merged | tamper tests plus recompute without gateway or DB | merged f1cbe01 6a89810 13 passed |
| M5 | live qualify | blocked | cap sheet plus frozen protocol plus E0 preflight | valid grant only | E0 apparatus control then E1 E2 if permitted E3 only if eligible reviser | blocked no grant |
| M6 | handback | coordinator main checkout | reports/PROJECT-LEDGER.md docs/design/REFINEMENT-ROADMAP.md completion matrix | all deterministic lanes merged | serial suite plus independent review plus push plus remote equality | in handback at 8148f6b final review ACCEPT |

## Merge rule

Serial no-ff merges on main checkout only. Rerun affected gates on tip. Parallel lane green does not imply integrated green. Late fixes get full review.

## Jev checkpoints

M0 design to code mapping. Shared executor and secrecy boundary before integration. Prospective comparison before freeze or launch. Final evidence and bottleneck ranking. Save sanitized JSON under reports/jev/invl02-*.json with disposition accepted rejected unresolved. Jev probability is opinion not pass proof or authorization.
