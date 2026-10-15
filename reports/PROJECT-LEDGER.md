# Project ledger

Current state and evidence. Removed studies are recoverable at
`archive/pre-subtraction-2026-10`; implementation history lives in Git.

## Research checkpoint (2026-10-14)

Human direction: accept the existing prototype at its scope and research stronger
components. Do not turn another brief live-route or improvement-proof campaign
into a prerequisite for architectural development. The destination remains
general autonomous investigation, executable capability acquisition and transfer,
accumulated experience and improvement of the learner.

Primary-source reading refreshed Dream-RSI and The Last AI Built by Humans,
with targeted HyperAgents, DGM, GEPA, memory/context, library-learning and
coordination research. [Research notes](../docs/design/COGNITIVE-RESEARCH-NOTES.md)
record reading scope and limitations. Papers inform the design; none proves our
combined architecture or its novelty.

The [architecture synthesis](../docs/design/ARCHITECTURE-SYNTHESIS-2026-09-22.md)
now selects one persistent investigation owner, versioned operational/learning
policies and the existing execution kernel. Its previous consolidation plan is
preserved in Git. The human requested separate plans so each part can work before
the next is built. The [master plan](../docs/plans/MASTER-PLAN.md) now owns their
dependencies and build order. The three research themes are divided into ten parts:

| Component | Current state | Working target |
|---|---|---|
| P01: persistent investigations | Working checkpoint; qualified below | One durable objective with continuing decisions and restart. |
| P02: evidence and memory | Working checkpoint; qualified below | Reusable evidence and revisable claims with opposition. |
| P03: context construction | Working checkpoint; qualified below | A bounded evidence-selection policy consumed by actual decisions. |
| P04: executable capabilities | Integrated; final independent review and live study pending | Construction, checked retention and later executable use. |
| P05: autonomous agenda | Planned | Experience changes what the system chooses to investigate next. |
| P06: search history and dreaming | Planned | Supported replay screens policies and identifies live coverage needs. |
| P07: learner revision | Planned | An inherited executable learner controls later successor production. |
| P08: temporary teams | Planned | Retained coordination controls dispatch, joins and rework. |
| P09: representations and transfer | Planned | Qualified abstractions execute on meaningfully changed work. |
| P10: continuing campaigns and assessment | Planned | Bounded unattended operation, resume and longitudinal evidence. |

These statuses describe the new component contracts, not the absence of reusable
prototype code. Every component plan has delivery slices and behavioral checks.
The component batches built P02 and P03 on the P01 checkpoint. Human
direction now requires consolidation and CI repair after every component,
followed by the next assigned part. P03 and its consolidation are complete.
P04 is now assigned; P05–P10 remain paused.

P02 task list:
- [x] Ground the existing observation, artifact and consumer paths; compare storage shapes.
- [x] Pin the evidence, claim revision, visibility and later-use contracts before code fan-out (`cff8c980`).
- [x] Implement immutable experience lookup and revisable lessons in isolated lanes.
- [x] Connect later investigations and qualify acceptance scenarios P02-A through P02-E.
- [x] Run independent GPT-6.1 Sol High verification and a bounded live contradiction probe.
- [x] Record exact evidence boundaries, remove owned worktrees and sync the checkpoint.
- [x] Consolidate P02, repair the archived restore CI failure, and confirm checkpoint CI (`c998c5d1`, run `38585414989`, all seven jobs green).

P03 task list:
- [x] Ground the consumer and compare two independent context-policy designs after the P02 gate.
- [x] Pin packet identity, allocation, inspection accounting and invocation contracts in the P03 plan.
- [x] Implement and integrate baseline context, bounded inspections and policy comparison.
- [x] Run integrated acceptance scenarios, then independent GPT-6.1 Sol High verification.
- [x] Run a prospectively bounded free-route comparison and report its actual limits.
- [x] Consolidate, repair CI, remove owned worktrees and sync backups before P04.

Current throughput checkpoint: P03 implementation, independent review, bounded
live comparison, consolidation and checkpoint CI are complete. Both backups are
synced. See the P03 checkpoint below for separate evidence classes.
The human authorized P04 after closure. P05–P10 remain paused.

P04 task list:
- [x] Ground. Trace genome publication, bounded child execution, investigation decisions and retained use.
- [x] Sketch. Compare two independently designed package/selection shapes and pin the chosen interface in the P04 plan.
- [x] Agree. Proceed under the assigned P04 scope; no additional design approval is requested.
- [x] Implement. Qualify independently authored execution, construction/checking, experimental retention and fresh-process use.
- [x] Scrap check. The selected ownership boundaries held; no replacement architecture was needed.
- [x] Run integrated P04-A through P04-E and neighboring P01–P03 checks.
- [x] Complete the experiment apparatus gate on the integrated source.
- [x] Finish independent GPT-6.1 Sol High verification after integration. All three findings are repaired and independently closed at `ba95df09`.
- [ ] Run one prospectively bounded free-route construction and later-use experiment; preserve negative outcomes.
- [ ] Consolidate, repair CI, remove owned worktrees and sync both backups.

P04 throughput checkpoint: the selected genome method ABI, broker-routed
construction, native method episodes, checked experimental retention and public
investigation selection/use are integrated. At `21f0dee9`, the combined P04 and
neighboring P01–P03 gate passed **49 tests in 687.41 seconds**, on real
PostgreSQL 18 and subprocesses. This is a focused gate, not a full-suite claim.
It includes no-op rejection, incompatible interface refusal, substituted-solution
rejection, immutable receipt recovery and fresh-process changed-input use.
Regressions exposed and repaired import-time output corruption, the nested
operation effect shape and kernel payload normalization during receipt recovery.
The runner returns one result; the episode consumer owns solution materialization.
At `183e1788`, all **36 P04 tests passed in 274.19 seconds** on PostgreSQL 18.
This includes the replayable campaign driver, offline checker and a fixture
constructor followed by checking, retention and three fresh-process changed-input
uses. It qualifies apparatus behavior, not live model acquisition. The gate also
includes the earlier runtime and constructor controls. Independent GPT-6.1 Sol
High review started only after this gate finished. No P04 live model call has run
yet. Both backups are synced through this source tip. GitHub CI run
`38663722417` passed all seven jobs at `183e1788`, including both database
shards, archived tests and all three portable operating-system jobs.
Independent review at `183e1788` found three material gaps. **P04-R1**
allowed construction recovery to replace already published bytes. The repair
`2e7fcb31` pins an existing genome artifact before lineage publication and
recovers from that snapshot, including previously published identical content.
Three crash-boundary regressions failed before the repair. **P04-R2/R3**
allowed positive and negative campaign claims without their native or constructor
receipts. The merged repair `2b5f0551` requires the actual operations, typed
outputs, task/solution-bound verifier results and constructor evidence. Its clean
fixture control passes while deleted receipts and swapped verifiers refuse.
The complete merged P04 gate passed **42 tests, zero skips**, in **278.35 seconds**
on PostgreSQL 18 with native subprocesses. Sol High's recheck accepted the
original operation-linkage controls and exposed one remaining R3 defect with a
real failing candidate. Ordinary failed tests produce failure receipts; the
checker had required success even when validating a rejection. The follow-up
repair binds each outcome to its typed worker status and recomputes failed,
error and skipped-test results. A real wrong-method campaign now accompanies
the successful fixture campaign. At `ba95df09`, the final P04 gate passed
**43 tests, zero skips**, in **285.53 seconds** on PostgreSQL 18. CI run
`38675671161` passed all seven jobs at that revision. Final independent
re-verification passed at `ba95df09`. Its real PostgreSQL/native probes passed
2/2 in 20.16 seconds; positive, negative and invalid-constructor controls
checked, and all six evidence-removal or contradictory-retention mutations
were rejected. No material finding remains within this review scope.
The prospective first study at `69716d9f` stopped before any model request.
The installed Codex catalogue no longer contains the launcher's default
`gpt-5.4` metadata template. The operation reconciled with never-sent proof,
zero receipts and zero consumed/reserved units. The driver/checker preserve
`unresolved`, not a model negative. Its frozen manifest and report are in
`experiments/capability04/evidence/live1/`. A narrow launcher compatibility
repair updates the metadata template without changing the free inference route;
its regression failed before the repair. The installed catalogue and prompt
isolation now pass without a model call. The affected gate passed 70 tests;
three campaign tests refused the deliberately dirty pinned source tree. The complete campaign and catalogue gate then passed **16 tests, zero skips**,
in **82.01 seconds** at `d18c67a5`, with the same source committed and no
assertion changes. Independent Sol High compatibility review passed at `d18c67a5`, including
2 independently rerun regressions, the installed-binary catalogue/isolation
probe and never-sent evidence. A fresh freeze precedes live inference.

The informative stopping condition is a working
acquire/check/retain/select/execute path with substitution, applicability and
restart controls, plus an attributable live outcome. A learning win is not a
completion requirement. Authored packages and model-acquired packages remain
separate evidence classes.

### P03 implementation and consolidation (2026-10-14)

`rsi.context` constructs one immutable packet per investigation state revision,
using P02 evidence and claims and the existing command journal. It keeps required
support and opposition together, selects optional bundles under the complete
canonical continuation budget, and caches completed bounded inspections. Adaptive
inspection can change its next query from an earlier result. P01 stores the exact
packet and binds it to the actual broker instruction; resume retains the admitted
decision and operation. Changed selected bytes or claim eligibility refuse the
affected new decision. The validate-only legacy adapter preserves the inherited
saved-memory contract for pre-P03 pending work.

The replaced memory builder/revalidator were removed from `investigate.py`.
Consolidation also removed premature comparison publication and an invalid sum
of CPU and token charges. Worker token usage stays separate from raw operation
costs. No new migration, service, context lifecycle or grant authority was added.

Coordinator verification on PostgreSQL 18 passed the combined builder, consumer
and migrated P02 gate with **24 tests, zero skips**, in 486.06 seconds at
`bf234616`. The complete nine-cell fixture comparison and result-shape regressions
passed **five tests** in 336.94 seconds at `19179650`, following repair of a real
late accounting bug caught by its first integrated run. Consolidation passed
**five tests, one matrix test deselected**, in 43.68 seconds at `9844d876`.
Neighbor checks separately passed 43 tests; a checkpoint failure caused by the
missing local `pg_dump` path passed its one-test rerun after environment repair.
These separate runs are not summed into a whole-repository result.

[GPT-6.1 Sol High review](../reviews/P03-REVIEW.md) independently passed seven
consumer tests, three source/withdrawal/legacy checks and a retained nine-cell
fixture baseline. It exposed source-freeze binding and grading-consistency gaps.
The repairs reject changed prospective hashes, changed or deleted observations
and grades missing their verifier reference. Final independent audit at source
`0800a14c` kept the clean baseline passing and rejected all six altered-data
controls in 3.40 seconds. Unknown usage and cost/token separation stayed correct.
The coordinator repeated five focused gates in 42.33 seconds before the final
omission guards; those guards passed three cheap regressions in 1.77 seconds,
with all three counterexamples accepted by the actual pre-fix source. An extra
lane matrix run was interrupted and contributes no passing result; its exact
leftover disposable database was removed. Ruff and whitespace checks passed.

The [live comparison](evidence/p03-live-20261014/README.md) ran once under
prospective freeze `543a0956`, with separate arm stores and shuffled order.
Six actual free-route workers yielded **three passes, one failed task and two
unavailable grades**. All three required-source-removal controls refused without
dispatch. The structured misleading cell retained the initial procedure and
failed its empty-input test. Adaptive misleading timed out; raw complete lost
its response stream. Ten target operations have ten settled receipts and no
exported unresolved effects. Five worker receipts report a known subtotal of
859,547 tokens; the missing stream usage leaves the full total unknown.
The 88-record/artifact archive passes standard-library-only recomputation with
gateway variables absent and a nonexistent database DSN. Raw duplicate export
directories were removed after byte verification. No unavailable cell was retried.

This qualifies authored context construction and live use at scope. It does not
establish a context advantage, autonomous policy acquisition, transfer, learner
improvement, provider billing, hostile-code containment or deployment. Logical
inspection counts do not measure all physical reads or interrupted CPU work.
All owned P03 worktrees and branches are removed. The nine new live databases
and private run area remain receipt anchors; older live anchors are unchanged.
Small completed scratch folders under `D:/AI/tools/p03` remain because automatic
approval review blocked their recursive deletion. They are outside the repository.

Final CI run `38632408127` passed all seven jobs on source/evidence checkpoint
`8ffc003b`. Committed-byte verification caught Git normalizing the frozen checker
snapshot's line endings; a scoped raw-byte attribute and re-add restored its
prospective digest. Standard-library recomputation also passed from a fresh Git
archive of that checkpoint. The closure commit changes status documents only;
it does not extend the source qualification. P04 was subsequently assigned.

### P02 consolidation (2026-10-14)

Source `c998c5d1` reuses one captured-observation lookup and one immutable set of
supported memory views. No broader dead path justified deletion. The audited
production consolidation removes five net lines across three files.

CI run `38581711770` had six green jobs and four archived restore failures.
The fresh-target fixture cleared only `control`, leaving P02's seeded clock row.
It now discovers and clears domain tables, preserving the production freshness
guard. Its real subprocess uses Python instead of the POSIX-only `/bin/true`.
The lane reproduced four failures before repair, then passed all four on PG18;
the coordinator repeated all four in 55.46 seconds. The consolidation lane passed
18 P02 tests in 384.42 seconds. The coordinator's combined gate on the merged
source passed all 22 P02/restore tests, zero skips, in 489.64 seconds, then removed
both disposable databases. CI run `38585414989` passed all seven jobs on
`c998c5d1`, including both database shards, three portable jobs and heavy archived
checks. Owned consolidation worktrees and branches are removed; both backups
contain the checkpoint. Existing live anchors and evidence remain unchanged.

### P02 implementation checkpoint (2026-10-14)

Implementation and independent review are complete at source `84385f7b`.
`rsi.experience` inventories original development observations with byte-verified
provenance. `rsi.memory` stores versioned interpretations, support, opposition,
derivation, withdrawal and supersession. Later investigation decisions pin one
memory revision and its actual content; resume retains that decision and
revalidates every selected original. Raw-history lookup and structured lessons
share this source authority. No embedding service or second lifecycle was added.

The independent review found a global refusal on incomplete discovery and an
ancestry walk that followed newer heads instead of declared parent versions.
Repairs preserve visible discovery warnings while refusing changed selected
bytes, and follow exact transitive ancestry with current withdrawal/supersession.
The coordinator also repaired immediate capture on error returns. Regression
checks failed before these fixes. A recursive-argument error in the first ancestry
patch was caught before merge and repaired with a transitive supersession check.

GPT-6.1 Sol High independently passed **18 component tests, zero skips**, in
324.89 seconds and **four adapted counterexamples** in 73.00 seconds on the
repaired source. They covered original evidence, opposition, withdrawn ancestry,
valid replacement descendants, as-of reconstruction, immediate refusal capture,
replay identity and selected byte tamper. A separate original-tip probe captured
257 genuine refused observations and demonstrated global blockage plus recovery;
it passed in 534.33 seconds. Its evidence is bound to `ae1dca44`, not the repaired
version. The final coordinator gate passed **120 tests with one skip** in
835.20 seconds on PostgreSQL 18.0, covering every `tests/test_rsi*.py` file plus
`tests/test_rec_checkpoint.py::test_checkpoint_writes_consistent_recovery_set`.
The skip names Windows symlink creation permission. Actual fixture child
processes ran; the checkpoint included migration `0030`. Changed Python files
passed Ruff, the diff passed whitespace checks, and the changed-file credential
scan was clean. No whole-repository, CI or deployment pass is inferred.

The [live memory probe](evidence/p02-live-20261013/README.md), source `ae1dca44`,
completed both actual free-route workers with passing pristine task checks.
The raw worker explicitly used an earlier failed empty-input case. The structured
worker received the challenged lesson and its original support/opposition. All
8 worker/verifier operations settled with 8 receipts. Live worker usage was
341,911 input and 2,347 output tokens. Package hashes, references and usage
agreement pass the offline archive check, independently repeated by Sol.
The prior observations were fixtures and the lesson was authored. The structured
cell also saw the preceding raw-cell result. This establishes live use at scope,
not a matched memory advantage, autonomous acquisition, transfer or learning.
Provider billing and hostile-code containment remain unverified.

At the P02 checkpoint, P03 context construction was assigned after the
consolidation and CI gate. P02 supplies its evidence objects and stable revisions;
learned ranking, automatic lesson construction and ongoing campaigns are not
claimed by this checkpoint. All owned implementation/review worktrees and task
branches are removed. Only the main checkout remains. The checkpoint is synced to
both backups; the source qualification above remains bound to `84385f7b`, and the
following closeout commit contains documentation and archived evidence only.

P01 task list:
- [x] Pin the state, decision and pending-effect contract against the existing kernel (`74f2b65f`).
- [x] Implement the investigation owner and identity-bound worker continuation.
- [x] Verify continuation, fresh-process resume, stale refusal, isolation and unresolved outcomes.
- [x] Migrate one existing task workflow, remove replaced ownership and deliver a verified checkpoint.

### P01 implementation checkpoint (2026-10-13)

`rsi.investigate` now creates, inspects, steps, suspends, resumes and exports a
development-task investigation. The kernel remains the objective and dispatch
authority. A one-to-one SQL extension owns the continuation revision, questions,
artifact references and pending decision; existing decision and attempt histories
record its actions and observations. Worker instructions bind the continuation
and saved solution bytes. The existing loop routes development work through this
owner with one action per task, preserving its frozen comparison budgets.

Eight acceptance scenarios cover checked continuation, fresh-process recovery
after worker settlement but before verification, stale decisions, concurrent
workspace isolation, invalid actions, token refusal, verifier refusal and proven
never-sent preflight failure. Definitive refusals become inspectable unresolved
results; uncertain effects retain their pending identity. These are distinct
outcomes. The task consumer remains a fixed bounded seed policy, not a learned
agenda or an unattended campaign.

Primary verification, source checkpoint `5888cb50`: **29 passed, zero skips**
across the final state, public acceptance and loop-refusal gates on disposable
PostgreSQL 18.0 databases with actual fixture child processes. A preceding broader
RSI regression run passed **99 tests with one Windows symlink-privilege skip**;
it preceded the final never-sent handling and its added acceptance scenario.
Those changes are covered by the final 29-test gate. A separate real checkpoint
test passed and included migration `0029`. Changed Python files passed Ruff and
`git diff --check`. No whole-repository suite or CI pass is inferred from these
checks. Luna implemented isolated lanes; the primary ran the final gates, with
an additional GPT-6.1 Sol High source/handler review of the material fixes.

[Live evidence](evidence/p01-live-20261013/README.md) records the free-route
continuation smoke and its limits. The first preflight was proved never sent;
the second envelope completed diagnosis but exceeded its token allowance. A fresh
larger envelope then completed two worker actions: diagnosis, a failed pristine
check, suspension, and fresh CLI resumption with the checked observation and saved
solution. The model changed subtraction to addition. The final verifier was
refused because the study's 120 CPU units covered only one 111-unit reservation.
That under-sized allocation is an experiment setup error. The investigation stays
unresolved; no final passing live verdict is claimed. No limit or earlier result
was rewritten to make it pass. P01's continuation mechanism is qualified; task
utility, transfer, learning benefit and hostile-code containment remain unproved.

All owned implementation worktrees and temporary lane branches were removed.
The live receipt anchor remains in `p01_live_20261013` on port 55432 and
`D:/AI/tools/p01-live-20261013`. P02–P10 were paused at the P01 checkpoint. Future continuation studies
should derive checker exposure from the broker's profile and allow for CLI input
overhead rather than treating wall time or a short task as the resource cost.

Build P01, then P02 and P03, then P04. P05 and P10 provide an early continuing
autonomous prototype before advanced replay, learner revision and teams.

The foundation prototype is accepted at its bounded scope. This does not close
Stage 10's general-autonomy or learning objectives, nor qualify deployment.
Short behavioral probes qualify mechanisms; continuing campaigns accumulate
utility, transfer and improvement evidence. No statistical gain is required to
finish an exploratory implementation, and no such gain is claimed here.

The initial planning checkpoint changed research documents only. The P01
implementation and its separate verification categories are recorded above.

## State (2026-10-08)

The aim is general autonomous discovery and agent improvement. This Python
bank is the first bounded experiment. Settlement owns execution, budgets,
receipts and artifacts. The editable genome contains Codex instructions,
skills, allowed harness settings and the improver's own instructions.

| Checkpoint | State |
|---|---|
| T1 route | User-approved free routes through Codex CLI. Direct OpenRouter is `openrouter/openrouter/free`; the bare `openrouter/free` alias goes through Kilo. |
| T3 genome | Content identity, lineage and restricted settings; meta instructions remain editable. |
| T4 episodes | Broker admission, process limits, skill-isolation preflight, token accounting and trajectory records. |
| T5 bank | Published tasks, fixed splits, frozen evaluators, pristine verification and solution snapshots. |
| T10 subtraction | Nine study modules and their callers/tests retired; 49 dead tables dropped by a forward migration. Operator pages inspect genomes, episodes and verdicts. |
| T6 archive | Every genome remains selectable; fixed sigmoid/children selection records scores, coverage, weights and draw. The latest unknown outcome cannot retain an older passing score. |
| T7 proposals | AI proposes a child using editable meta instructions and pinned dev-only evidence. Invalid outputs and execution failures remain recorded. |
| T8 gate | Frozen scope, model and budgets; validation, solved-task regression and fresh paired anchor comparison. Benchmark gains are experimental; trusted mode requires containment. |
| T9 loop | Bounded, replayable archive exploration and an operator CLI. A live child was acquired and used through the public proposal/episode/verifier functions. The authored smoke task passed; task-bank competence, automatic full-loop acceptance and retained gains remain unproved. |
| T11 synthesis | AI proposes tasks from observed dev failures. The fixed qualifier requires a passing reference and failing stub before dev publication. Pinned outputs survive interrupted verification. |
| T12 delivery | Checkpoint commits and operator docs; local gates below. [CI status](https://github.com/RoyCoding8/Stray-repo/actions/workflows/ci.yml) is tracked per pushed commit. |

## Evidence

Reviewer checkpoint, 2026-10-08: all seven CI jobs passed on the delivered
a3094099 revision, run 37730286147. Read-only inspection of live store rsi_t5
found two completed episodes with failed test verdicts, three timed-out episodes,
one failed and one timed-out proposal, one root genome and zero anchor exposures.
There was no live child or improvement result at that review checkpoint.

Two review defects were reproduced and repaired. Archive exploration compared
a child only with its selected parent, so a gain over a weak node could replace
an equally good incumbent. The loop now compares against its current incumbent;
archive parent selection still controls proposal generation. Missing or invalid
completed-turn usage became zero tokens. It now stays unknown and charges the
reservation ceiling, with replay proving no second send or charge.
The six initial regressions failed before repair. The final affected gate passed
32 tests with no skips on disposable PostgreSQL 18.0 databases and real fixture
children; both databases were dropped. No new model calls ran. Follow-up CI passed
on repair commit c06e16d5, run 37745626153, separately from the delivered revision's
green CI. Ruff was unavailable locally;
changed Python files parsed and git diff --check passed.

Free-route checkpoint, 2026-10-08: [live evidence](evidence/rsi-live-20261008/README.md)
records 13 broker-routed agent operations and 3 verifiers, all with terminal
receipts, plus two separate HTTP text probes. Direct OpenRouter acquired child
`8c1a73e414e7fb304dfcded548cce6b4c005bca60ec6cbac47c8a0181afcccde` from pinned
development evidence. Its changed instructions were reloaded unchanged in a
fresh process and passed pristine verification on an authored addition smoke
task. The seed also passed that task. The child's Grade School attempt timed
out; other task-bank attempts failed, timed out or exceeded their budgets.
This proves a live acquire/retain/use/check path on the smoke task, not a gain,
transfer, executable-skill acquisition or improved improver. No comparison ran,
no anchors were exposed and nothing was promoted.

The router budget compatibility repair passed 10 targeted tests without skips
on disposable PostgreSQL 18 databases. Source commit `5c2f1f32` passed CI, run
37751042389. Router attempts used one request/stream retry. Published router
prices were zero; provider invoices and chosen underlying models were not
measured. Unknown usage remains unknown and is ceiling-charged. Known Super
usage exceeded its reservation, so the recorded usage and book charge differ;
that operation stayed unscored. All 24 study allocations have zero reserved
units. Preserve the owned `rsi_live_20261008` database and external run root
`D:/AI/tools/rsi-live-20261008` as evidence. The older `rsi_t5` store was unchanged.

The local workspace now has one branch and one registered checkout. Nine stale
remote branch snapshots were tagged on both remotes before deletion, and a
verified all-ref bundle is under D:/AI/Agent-Society-archives/2026-10-08.
Origin's legacy default branch remains for clone compatibility. The current
worker prompt and refinement roadmap supersede the old JSON/EC02 assignments.

The frozen Exercism bank has 34 tasks: 18 dev, 5 val and 11 anchor. All 34
references passed and all 34 stubs failed in actual verifier processes,
without model calls. Bank digest:
`fe81ef1f56941acf910ca7f1ee9a53ac168bfc05e985938d1e70fffe972f5f43`.
See [bank evidence](evidence/rsi-t5/bank-report.json).

The real native runs used `nvidia/nemotron-3-ultra-550b-a55b:free` on the
approved local gateway. Three task episodes timed out; one improver attempt
also timed out. There were no scored task outcomes, child genomes, gates or
anchor exposures. No model-led improvement or curriculum growth is proved.
Consumed tokens on these failures are ceiling charges, not measured model
usage. See [live evidence](evidence/rsi-t9/report.json). Recovery artifacts
remain in DB `rsi_t5` on port 55432 and `D:/AI/tools/rsi-t5`.

The follow-up authenticated `localhost:4000/v1/models` check returned HTTP 200.
Two Proverb executions using `cohere/north-mini-code:free` completed in 79.2
and 200 seconds. Both failed pristine tests. The bounded loop's improver then
received HTTP 400 because the provider rejected malformed tool arguments in
conversation history. No child, gate or anchor exposure followed. The original
receipt remains `failed`; the corrected parser classifies its actual trajectory
as `infra_failed` and meta results now retain the provider reason. See the
[route diagnosis](evidence/rsi-t9/route-check.json) and
[loop report](evidence/rsi-t9/cohere-loop.json). Gateway availability and completed
execution are proved; task competence and model-led improvement remain unproved.
The provider-classification and meta-reason changes passed 19 focused
PostgreSQL tests across episodes, proposals, loop and synthesis. Replaying the
live loop retained its report values and the recorded send/exposure counts.

The kept Windows/PostgreSQL suite passed **513 tests, with 20 skips** before
final attribution and timeout-test edits. Archived heavy tests were excluded.
The final loop/synthesis check passed **6 tests**, covering the new timeout
case, separate AI/fixed attribution, and qualification recovery. These are
separate verification scopes. The changed new modules and fixtures passed
Ruff checks. A separate real bank-import test passed for LF-only summary
exports, and a recorded native CLI run replayed without a new send. The shared
artifact-path fix then passed **35 focused tests, with 3 symlink skips** on
Windows. Member paths reject Windows drives and backslashes on every OS.
Final delivery requires matching remotes and green CI on the
pushed commit; see the CI link above and the current continuation handoff.
Executable fixtures test proposal, gate, synthesis and replay behavior;
they do not establish AI learning. A fixture solver ran the full benchmark
gate through actual pristine verifiers and received `experimental_gain`.
Strict mode blocked before model execution.

Proven unsent refusals release their reservations through the existing
never-sent reconciliation transition. They receive no fabricated receipt or
task verdict. Unknown dispatches retain their exposure.

## Boundaries and next experiment

Human direction, 2026-10-08: the live route has enough qualification for research
use. Stop treating route proof as a separate campaign. Check availability once
at the start of a live experiment, then use actual task and learning runs to
observe failures. Reopen transport diagnosis only when a concrete failure makes
the result uninterpretable. Preserve attribution without expanding it into
another infrastructure project.

The 2026-10-13 research checkpoint above supersedes the earlier next-task priority.
Completed task competence and fair comparison remain useful evidence targets,
not prerequisites for designing the missing cognitive mechanisms. A fair negative
can complete an experiment without completing the learning objective.

- Stronger sandboxing is deferred at the user's request. Native process-tree
  and resource limits remain; filesystem/network containment is unproved.
  A native probe denied a protected file read but still reached localhost
  PostgreSQL. Trusted promotion therefore remains disabled on these launchers.
- Each anchor content identity can be exposed to only one comparison,
  including interrupted runs. Renaming a task or resetting an epoch cannot
  refund exposure. The paired sign rule and alpha spending are recorded.
  This is conservative fresh-content accounting, not REUSE's reusable
  holdout algorithm or proof of general improvement.
- Timeouts stay unscored. Dev workflow failures can inform an improver;
  infrastructure failures stop the run. Acceptance requires completed agent
  executions and known verifier outcomes at every stage.
- Synthesized tasks receive fixed qualification independently of AI proposal
  attribution. Qualification does not prove that AI-written specifications
  and tests are correct. Held-out content duplicates are rejected; accepted
  tasks can enter a future dev task set without changing a frozen epoch.

P03 subsequently completed after P02 consolidation and CI repair, as recorded above.
Prospective utility comparisons must account
for free-router variation and include an unchanged-copy control where relevant.
Do not re-dispatch closed operations or refund allocations. Live instruction
acquisition is demonstrated; executable-skill utility and learning advantage
remain unproved. Isolation remains separate qualification work.
