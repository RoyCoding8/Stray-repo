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
| T6–T9 improvement loop | Archive selection, meta-agent proposals, acceptance gate and matched-budget anchor comparison remain to build. |

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

## Next

1. T6 archive and parent selection. Keep every node selectable and record the
   fixed selection rule separately from AI decisions.
2. T7 meta-agent. Propose a child genome from dev evidence and editable
   `meta/IMPROVE.md`. Exclude anchor content and trajectories from its inputs.
3. T8 frozen acceptance gate. Validation, solved-task regression, anchor and
   adaptive-reuse accounting; promote or quarantine.
4. T9 real closed loop. Compare the promoted genome and parent on the anchor
   at matched budget. A mock run does not demonstrate self-improvement.
5. T10 retire study controllers/tables after migrating `api` callers; T11
   verified task synthesis. Update docs and run CI with each checkpoint.

## Known gaps

- The local verifier bounds processes but has no filesystem/network
  containment. These cooperative benchmark verdicts cannot certify hostile
  code for promotion. That boundary must be addressed before a trusted gate.
- Infrastructure failures without usage events charge the token ceiling.
  Metering may be needed before T9.
- Codex preflight refusal leaves a reservation held until kernel recovery.
- Legacy `agenda`, `authority`, `loop`, `trials` and `evaluation` remain
  entangled with `api`; retired study tables remain in historical migrations.
- A 34-task Python exercise bank is a bounded experiment. It does not define
  the intended scope of general autonomous discovery and improvement.
