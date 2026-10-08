# Project ledger

Current state, next work and known gaps. History lives in Git; removed studies
are recoverable at `archive/pre-subtraction-2026-10`.

## State (2026-10-07)

The system aims to improve agents and their own improver with trustworthy
evidence. Codex CLI is the task-agent component. The editable genome contains
instructions, skills, harness settings and meta-agent instructions. Settlement
owns execution, budgets, receipts and artifacts outside agent modification.

| Checkpoint | State |
|---|---|
| T1 route | Codex CLI runs on the user-approved local free-model route. |
| T3 genome | Content-addressed packages, lineage, restricted settings and workspace materialization. |
| T4 episodes | Broker-admitted agent runs, bounded execution, skill isolation preflight, token accounting and trajectory artifacts. |
| T5 bank and verifier | Published tasks, deterministic splits, frozen evaluator versions, solution snapshots and separately admitted pristine verifiers. Completed episodes produce persisted verdicts; infrastructure failures do not receive a task score. |
| T10 subtraction | Retired nine study modules, migrated operator views, and added a forward drop for 49 study tables. RSI artifacts receive durable holds in their recording transactions. |
| T6 archive | All published genomes remain selectable. Fixed sigmoid/children selection records its dev task set, node weights and draw; replays retain their original parent. |
| T7 proposals | Codex edits a child genome using the parent’s editable meta instructions and a pinned dev-only evidence package. Outputs, invalid proposals and execution failures are recorded and replayable. |
| T8–T9 improvement loop | Acceptance gate and matched-budget anchor comparison remain to build. |

T5 evidence: the local 34-exercise Exercism bank has 18 dev, 5 validation and
11 anchor tasks. All 34 references passed and all 34 stubs failed through real
bounded verifier subprocesses, without model calls. The frozen bank is
`fe81ef1f56941acf910ca7f1ee9a53ac168bfc05e985938d1e70fffe972f5f43`.
This qualifies the bank plumbing, not learning or general capability.
See [bank evidence](evidence/rsi-t5/bank-report.json).

Verification on Windows with PostgreSQL 18: the kept suite passed 598 tests
and skipped 19 before the final path/replay checks, excluding archived heavy
tests. The final RSI gate passed 32 and skipped 1 because symlink creation was
unavailable. No new CI result is claimed. Fake-Codex tests check plumbing only;
T4's real model run is recorded separately in `tmp/HANDOFF.md`.

T10 verification: the kept run had 493 passes, 20 skips and one error-message
assertion failure. The corrected rejection and all later cleanup edits passed
a focused 62-test Windows/PostgreSQL check. Archived heavy tests remain outside
that verification scope. No cleanup CI result is claimed.

T6 verification: three focused Windows/PostgreSQL tests passed. This proves
selection and decision replay plumbing, not model-led improvement.

T7 verification: 20 focused Windows/PostgreSQL tests passed, including changed,
invalid, unchanged and infrastructure-failed proposals, replay, genome identity,
and exclusion of validation/anchor episodes from the evidence bundle. These
use an executable fixture; no model-led improvement is claimed.

## Next

3. T8 frozen acceptance gate. Validation, solved-task regression, anchor and
   adaptive-reuse accounting; promote or quarantine.
4. T9 real closed loop. Compare the promoted genome and parent on the anchor
   at matched budget. A mock run does not demonstrate self-improvement.
5. T11 verified task synthesis. Update docs and run CI with each checkpoint.

## Known gaps

- The local verifier bounds processes but has no filesystem/network
  containment. These cooperative benchmark verdicts cannot certify hostile
  code for promotion. That boundary must be addressed before a trusted gate.
- Infrastructure failures without usage events charge the token ceiling.
  Metering may be needed before T9.
- Codex preflight refusal leaves a reservation held until kernel recovery.
- A 34-task Python exercise bank is a bounded experiment. It does not define
  the intended scope of general autonomous discovery and improvement.
