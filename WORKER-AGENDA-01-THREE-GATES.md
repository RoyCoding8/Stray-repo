# Worker: finish three Agenda 01 acceptance gates

Fetch and explicitly integrate `origin/codex/agenda-assessment-02` into your owned `codex/implementation-agenda-01` branch. The reviewed implementation is `051811fd59ab6d1de0f85a1be8849e94b638ebf5`. Preserve current work, use normal commits/pushes, and never reset or rewrite another task's branch. This prompt is sufficient for a new chat.

Read [the assessment](reviews/AGENDA-01-CORRECTION-ASSESSMENT.md), its linked executable probe/JSON, the [original implementation contract](docs/design/AGENDA-01-IMPLEMENTATION.md), and the [experiment protocol](docs/design/AGENDA-EXPERIMENT-01.md). Existing collaboration and implementation workflow rules still apply. This is not another whole-repository audit.

Retain the corrected substrate, receipt linkage and Q-only policy intervention. Three acceptance gaps remain. Confirm or rebut each with evidence, then complete it. Prior reports marking all six previous findings closed must be qualified where their acceptance evidence was insufficient.

## Phase A: short gates before another expensive run

1. **AGR2-01, genuine resume.** The current test omits `--resume` and therefore drops/recreates the database. Fix the real path and its test, not only its label. The driver also saves the next tick before persisting the current tick record. Prove continuation in a fresh process by preserving a unique database sentinel and comparing durable decisions, effects and costs. Exercise interruption after admission but before receipt, pending observation and the progress boundary. A fresh deterministic rerun cannot pass this gate.
2. **AGR2-02, decision charges and time.** w08–w11 contain 268 distinct uncharged policy decisions across 16 traces. A new decision that discovers a duplicate effect still costs one unit; redelivery of the same committed decision costs nothing extra. Unify the declared decision/time semantics used for external events, delayed receipts and horizon eligibility. Prove this with the affected worlds and small delayed-effect probes. Do not backfill totals or move observation timestamps to make a fence pass.
3. **AGR2-03, frozen execution and rejection checks.** Run from a specified verified frozen manifest/source, not an unchecked current rebuild. Let unchanged frozen source remain replayable after documentation-only commits. Reject `complete=false`, duplicate whole trajectories, missing decision references/charges, entire missing pairs, changed manifest/source and horizon contamination. Prove these mutations fail under strict final-panel mode. Development/subset runs must be explicit.

The supplied probe is a characterization of the reviewed defects, not the full acceptance suite. Convert its findings into meaningful maintained regressions and run the real PostgreSQL seams. Review what the test actually executes: flag defaults, database recreation, saved progress order and receipt state must be asserted, not assumed from names.

## Phase B: one interpretable completion

After the three short gates pass and an independent reviewer checks their actual paths, preserve v1/v2 evidence and freeze the corrected apparatus before running the full panel. Keep the chosen workload and analysis unless the timing correction requires a disclosed versioned change. Q may help, tie or lose. Report all results and failures; never selectively rerun favorable pairs.

Run the affected integration checks and full suite on the final production/experiment source. Record exact revisions and any subsequent changes honestly. Update `reports/PLAN.md`, `reports/AGENDA-01.md`, `reports/VERIFICATION.md`, `reports/IMPLEMENTATION-STATUS.md`, `reviews/REQUEST.md` and the roadmap. Derive totals from committed traces; the current report's copied family totals do not all match its revised pair table.

Parallel specialists are authorized with distinct owned paths/worktrees/databases and exact skill/requirement instructions. Put shared driver/time semantics under one owner. The coordinator alone integrates and edits shared reports. Before replacing a silent agent, establish that the previous writer has stopped.

Commit/push normally to `codex/implementation-agenda-01`, verify remote equality, and report the final SHA plus the three gate results and experiment verdict. Use private author and committer `Nightjar <nightjar@authors.invalid>`, configured remote names, and no credentials in Git. Preserve executable drivers and bounded evidence before removing only your own disposable test resources.

Stop when these gates and the corrected experiment have evidence. Representation invention, teams, learner revision, deployment qualification and a broader live study remain outside this assignment.
