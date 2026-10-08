# Project ledger

Current state and evidence. Removed studies are recoverable at
`archive/pre-subtraction-2026-10`; implementation history lives in Git.

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

The next work is Stage 9 task competence and useful revision, feeding Stage 10.
Start with clear public interfaces and a small development set that completes
within its budget. Use its failures to acquire and test a revision, then assess
it on fresh content against the incumbent. Instruction revisions are valid
experiments, but the broader destination includes executable skills and reusable
experience. Do not require statistically established improvement before every
design iteration; distinguish exploratory evidence from a promotion claim.
Stop an exploratory batch with completed behavior and an informative result,
or a diagnosed blocker that determines the next design change. A fair negative
can complete an experiment; it does not complete the learning objective.

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

Next evidence target: establish completed task-bank competence with a clear
public task interface, then fairly assess the retained revision against the
incumbent on fresh content. The free routers are stochastic services, not pinned
backbones; prospective comparisons must account for that variation and use an
unchanged-copy control. Do not re-dispatch the closed study's operations or
refund its allocations. Stop with either an attributable completed comparison
or a diagnosed blocking failure. Acquisition is now demonstrated; utility and
learning advantage remain unproved. Explore stronger native
or container isolation as a separate future checkpoint. No WSL is required
for the current benchmark.
