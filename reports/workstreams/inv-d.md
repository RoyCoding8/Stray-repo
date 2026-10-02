# INV-D: old-call reconciliation and new-study cap sheet (live prep)

Lane D prep, worktree `.worktrees/inv-d`, branch `wt/inv-d-liveprep`, base `5f75ef6`.
Scope is reports only. No `src`, `experiments`, `tests`, or `scripts` file was touched in this lane (verified by `git status` showing only this note).
Every count below carries its evidence or its label in the same sentence.

## 1. Old-call reconciliation (committed evidence plus lane A ledgers)

Sources read this session (measured file list): `reports/workstreams/inv-a-c2-ledger.json`, `reports/workstreams/inv-a-c4-ledger.json`, `evidence-live/c2-acquisition6.json`, `evidence-live/c2-acquisition8.json`, `evidence-live/c2-acquisition8-repair.json`, `evidence-live/c2live7-run.log`, `evidence-live/c2live8-run.log`, `evidence-live/c2live8-repair.log`, all 96 files under `evidence-live/c2-fallback/episodes/`, all 11 pairs under `evidence-ad01/c4-live/`, and `evidence-ad01/c3-trajectories-merged/` with its summary plus 6 campaign, 6 repertoire, and 6 use files.

### EC02 C2 live acquisition

c2live6 spent 2 construction calls of 4 authorized (measured in-export accounting), with 204 episodes declared in its own export grant field (measured value, self-reported provenance, no grant document committed).
Its 4 validation rows cover 2 lineages times init plus repair (measured row count), but both repair rows restate the init artifact as already published (measured `profile_reason`), so distinct model calls are 2 (inferred from restated rows).
Caller-counted cost per row is 18 sandbox ops and 0 model tokens (measured in every row), giving 72 sandbox ops across rows (measured sum) with distinct executions unknown (unknown label, repair rows re-validated a published artifact).
Lineage 1 failed stopped probe-only and lineage 2 failed policy-invalid on plan shape (measured failure fields).
Selection ran the local `coord02-dev-select/1` selector to none (measured selection field), costing 0 model calls (inferred from selector being local code, no operation recorded).
Use phase calls were 0 (measured outcome, selection none).

c2live7 admitted 48 episodes and 4 construction calls in its run log (measured log content) then crashed with `EXIT=1` on `ConstructionBudgetExhausted` (measured log content).
Consumed versus reserved spend for c2live7 is unknown (unknown label, crash preceded settlement).
No export file exists beyond the log (measured absence).

c2live8 init spent 2 of 4 calls and repair spent 4 of 4 with 0 refused (measured run log plus repair log ledgers), against 48 admitted episodes (measured log grant).
Sandbox spend on init validation was 18 ops for lineage 1 and 25 for lineage 2 (measured rows), and both repairs were unusable at parse (measured `repair_parsed_ok false`), so repairs added 0 sandbox ops (inferred from parse failure preceding validation).
Caller-counted model tokens were 0 on every row (measured).
Both lineages received lineage 1 probe-only text as repair feedback while lineage 2 schema failure was never delivered (measured ledger G7 defect record).
Effort high is recorded only for the repair round (measured repair export field), and init effort, model id, and gateway route are unrecorded (unknown label, no committed field).

c2-fallback holds 96 baseline episode files across arms A, F, L, and S at 24 each over 12 tasks times 2 repeats (measured file count and names).
Summed caller-counted costs are 96 model calls, 9600 input plus 1920 output token units, 480 sandbox ops, and 96 tool invocations (measured sums of in-file cost fields).
These are non-live fixture executions carrying a lane-E declared freeze (measured freeze file note), so they contribute 0 live gateway calls (inferred from absence of gateway operations plus declared baseline status).
Comparison calls beyond the local selector were 0 for C2 (measured absence of any comparison operation).

### AD01 C4 live qualification

11 JSON plus log pairs exist, 9 readable, 2 empty stubs (measured directory listing).
`trace-w0-R-live11.json` is zero bytes with an assertion log showing a task family mismatch inside the runner (measured log content), which is an implementation failure rather than infrastructure loss (inferred from assert location in committed control code path).
`trace-w0-R-live13.json` and its log are both zero bytes with no surviving cause (measured sizes), so its outcome is unclassified (unknown label).
Attempts live4, live5, live6, and live12 have no pair at all (measured absence confirmed by the lane A ledger).

Per-operation accounting totals across the 9 readable traces give 40 model calls (measured sum of per-op `model_calls`).
Of these, 27 are learner calls at 3 per trace (measured per-op ids), 13 are construction calls (measured per-op ids: I trace 3, resume 2, live8 4, live10 4), split into 7 init and 6 repair (measured op id suffixes), and 5 validation entries carried sandbox only with 0 model calls (measured ops: I trace 1, live10 4).
Settled per-operation tokens sum to 17383 (measured sum: I 1884, resume 1841, live7 1867, live8 4529, live9 2060, live10 5202, live14 0, live15 0, R baseline 0).
Only live7, live9, and live10 carry settled aggregate totals (measured non-null totals 1867, 2060, 5202), while 6 of 9 traces carry null aggregates (measured nulls), so study-wide token spend above the settled floor is unknown (unknown label).
Witness queries total 20 measured (measured sum: I 1, resume 2, live8 1, live9 15, live10 1).
Sandbox ops total 5 measured (measured sum: I 1, live10 4).
Episode dispositions total 21 no-candidate, 4 rejected, 2 inspected, and 0 retained across world 0 only (measured sums of mechanism plus episode fields).
No-candidate episodes fall back to the incumbent (measured episode fallback fields), while live14 and live15 carry all-null charge plus tokens on every learner op (measured nulls) and are therefore unclassified as provider versus transport cause without transport evidence (unknown label, ledger concurs).
Use phase records are 0 and retained repertoire is 0 (measured fields), so historical use calls are 0 (measured).
Historical calibration calls are 0 because no old campaign ran a calibration phase (measured absence across all C2 and C4 evidence).

### AD01 C3 callback corpus (doubled, zero live spend)

The merged corpus is canonical with 6 trajectories and 72 use records across 6 files (measured summary plus 12 records in each of 6 use files).
It spent 15 construction model calls against doubles (measured summary) with 0 learner model-inference calls through the bypass era driver (measured B1 IR-02 finding).
Its 72 use executions ran at 0 model calls (measured use accounting), with 45 sandbox ops, 150 doubled token units, and 234 witness queries (measured summary sums).
The `c3-trajectories` and `c3-authored` directories repeat the same worlds, arms, and tasks (measured summaries) and are same-scope variants rather than additional live spend (inferred from matching task sets plus doubled or fixture provenance), contributing 0 further live calls (inferred).

### Cross-cutting unknowns (measured absences, not filled)

Raw model text survives for no live EC02 construction call and no live AD01 learner or construction call (measured absence, lane A G1).
No receipt plus input linkage exists in-repo for any live call (measured absence, lane A G2).
No frozen per-episode effective configuration and no per-episode source revision were committed anywhere (measured absence, lane A G3).
Every AD01 R trace reuses campaign `ad01-w0-R-00` with operation ids carrying no database identity, so the file name is the only retry distinguisher (measured id shapes, lane A G4).
Sandbox or source time and wall time are unrecorded for every historical call because no log, trace, or ledger carries durations or timestamps (measured absence across all files read).
Gateway-side usage behind null-token operations, the crashed c2live7 attempt, repair reroutes, and all unrecorded live4 through live15 spend remain unknown liabilities (unknown label, lane A ledgers concur).
Old grants do not cover the new study because c2live grants were per-attempt campaign scoped and the 260000 AD01 agenda units are report-declared without a grant document or cross-database aggregate (measured ledger fields), and the one-root rule keeps authority on a single new study root (measured B2 envelope rule).

### Old-call totals

Historical construction calls: 2 (c2live6) plus unknown crashed (c2live7) plus 4 (c2live8) plus 13 (C4) plus 15 doubled (C3, zero live) equals 19 live construction calls settled plus 1 crashed attempt with unknown settlement (measured sums with stated unknown).
Historical repair calls inside that total: 0 distinct new-model repairs (c2live6 restated) plus unknown (c2live7) plus 2 (c2live8) plus 6 (C4) equals 8 live repairs settled (measured with stated unknown).
Historical learner calls: 27 live (measured C4 per-op sum) plus 0 admitted in C3 bypass era (measured B1 finding).
Historical comparison model calls: 0 (measured absence of comparison operations in every corpus).
Historical use calls: 72 doubled executions at 0 model calls (measured C3) plus 96 non-live fallback baseline executions (measured c2-fallback) plus 0 live use records (measured C2 and C4 outcomes).
Historical settled token floor: 17383 AD01 per-op tokens (measured sum) plus 11520 fallback declared units (measured sum) plus unknown gateway-side and null-token exposure (unknown label).
Historical sandbox, source, and wall time: unknown (measured absence of durations).

## 2. New-study cap sheet (INVESTIGATION-01 Qualification 6 plus paragraph 64)

Study shape is 2 calibration trajectories with one per domain plus fresh-process use each, then a frozen matched qualification of 4 comparison trajectories from I and R arms in each of 2 fresh worlds (measured Qual 6 text).
Each comparison trajectory carries 3 visible development tasks per domain and 6 protected use tasks as 2 within-scope plus 1 structural-transfer per domain (measured Qual 6 text), giving 24 final use records (measured arithmetic 4 times 6).
Manifests and policies freeze after calibration and before protected exposure with no new seeds selected from protected results (measured Qual 6 text), and freezing itself costs 0 model calls (inferred from local repertoire serialization path).
Per-trajectory binding caps are 6 decision boundaries, 3 development episodes, 2 candidate lineages with 1 initial plus at most 1 repair each, and 60 total model calls including diagnosis, context, and use calls (measured paragraph 64 text plus measured code defaults for `max_boundaries` 6, `DEV_EPISODE_CAP` 3, `MAX_LINEAGES` 2, and `model_calls` 60).

### Planned call counts

| Phase | Trajectories | Construction init | Construction repair | Learner proposes expected | Model-call ceiling |
|---|---|---|---|---|---|
| Calibration, 1 per domain through fresh-process use | 2 | 4 or fewer | 4 or fewer | 12 or fewer | 120 or fewer |
| Frozen matched comparison, I and R in 2 fresh worlds | 4 | 8 or fewer | 8 or fewer | 24 or fewer | 240 or fewer |
| Study total | 6 | 12 or fewer | 12 or fewer | 36 or fewer | 360 or fewer |

Construction totals 24 or fewer study-wide (measured paragraph 64 ceiling), with repair a subset of 12 or fewer (inferred arithmetic 2 lineages times 6 trajectories).
Learner proposes expect 36 or fewer at 1 per boundary (inferred from measured C4 precedent of 1 propose per boundary times 6 boundaries times 6 trajectories), inside the 360 ceiling (measured ceiling).
Use executions total 36 or fewer as 24 protected records plus at most 12 calibration-use executions under the same 6-task shape (24 measured arithmetic, 12 inferred cap where calibration use task count is unrecorded).
Use executions cost 0 model calls expected (measured C3 precedent of 72 use records at 0 model calls plus measured `run_use` path issuing no model-inference operation).
Eligible failures retry only inside the declared budget with no limit expansion after observing protected results (measured paragraph 64 text).
An empty repertoire executes the declared incumbent-use phase (measured `run_use` member-None path selecting incumbent plus measured C4 fallback precedent).
No-candidate and transport failure stay different outcomes because settled refusals carry reasons while unsettled null-token calls carry no transport evidence (measured C4 live7 and live9 reasoned outcomes versus live14 and live15 all-null ops).

### Token totals

Each learner call exposes about 2.6k units at current prompt sizes (measured lane B1 finding honored here).
Each construction call exposes about 4.1k units from the 8192-char prompt budget share plus 2048 output tokens (inferred from measured broker exposure formula of chars divided by 4 plus `max_output_tokens` times measured `PROMPT_BUDGET_CHARS` 8192 and measured 2048 defaults in learner and construction code).
Expected operating exposure is 36 learner calls times 2.6k plus 24 construction calls times 4.1k for about 192k units including output (inferred arithmetic 93600 plus 98328).
Expected output subset is 60 operating calls times 2048 for 122880 tokens or fewer (inferred arithmetic).
Authorized absolute ceiling is 360 calls at construction size for about 1.475M exposure units including output (inferred arithmetic 360 times 4097), never an expected spend (inferred label).
Post-effect receipts reconcile measured spend per operation (measured broker receipt path), and unknown exposure stays reserved or refused per existing rules (measured design text).

### Query, sandbox, source, and wall totals

Diagnostic witness queries cap at 16 per trajectory by default (measured `diagnostic_queries` 16 code default), giving 96 or fewer study-wide (inferred arithmetic).
Use-phase queries expect 96 or fewer from the measured C3 precedent of 31 to 47 queries per 12 records applied to 36 use executions (inferred arithmetic), giving 192 or fewer witness queries study-wide (inferred ceiling).
Sandbox plus source time caps at 3240 seconds or about 0.9 hours from 24 constructions times 3 tasks times the 30-second member timeout plus 36 use executions times 30 seconds (inferred arithmetic from measured `DEFAULT_TIMEOUT_MS` 30000).
Wall time carries an absolute ceiling of 108000 seconds or 30 hours from 360 calls times the 300-second gateway deadline (inferred arithmetic from measured `deadline_ms` 300000 in learner and construction code), with realistic operating time far below and uncommitted (inferred label, no historical duration evidence exists).
No host candidate execution and no unreported profile fallback are permitted inside these ceilings (measured paragraph 64 plus Qualification 4 text).

## 3. Live configuration discovery (new environment only)

`config/.env.example` documents setting names only and holds no endpoint address, key, database name, or spend permission (measured file content).
`SETTLEMENT_DSN` carries a local Postgres default (measured file content), while `SETTLEMENT_GATEWAY_ENDPOINT` is empty (measured file content) and `SETTLEMENT_GATEWAY_KEY` names only the holding variable with the key itself kept out of git (measured file comments).
`SETTLEMENT_ARTIFACT_ROOT` and `SETTLEMENT_STAGING_ROOT` name local paths only (measured file content).
No endpoint, key, database name, or spend value was copied from any old report into this note or any file (verified by inspection of this note plus `git status` showing no other change).
Model identity, effort level, and per-episode frozen configuration recording remain unset for the new study (measured absence in this environment).

## 4. Single concrete authorization request

Authorization is requested for the new INVESTIGATION-01 Qualification 6 study on one fresh study root covering 6 trajectories with ceilings of 360 total model calls, 24 construction calls with at most 12 repairs, about 192k expected token exposure within a 1.475M absolute ceiling, 192 or fewer witness queries, 0.9 hours or less of sandbox plus source time, and a 30-hour wall ceiling, requiring provision of `SETTLEMENT_GATEWAY_ENDPOINT`, the bearer key behind `SETTLEMENT_GATEWAY_KEY`, a fresh disposable Postgres grant named for the new study root, and written confirmation of the study root plus model id plus effort level plus per-episode frozen configuration recording before any live call.
