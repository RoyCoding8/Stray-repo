# AG01-DEMO workstream report (AG01-12)

Task: visible CLI path + operator read-surface demonstration.
Base: `769aeef14004ad6123f6f5a142df7ce666c6bfb3`.
Code commit: `03b15fc` ("AG01-12 demo CLI + journey test", this branch).
Tip: this report commit on `codex/ag01-demo` (docs-only follow-up; code under
review is the commit above).

Owned paths (only files created; no other source file touched):

- `scripts/agenda01.py` (argparse, stdlib + repo deps only)
- `tests/test_ag01_demo.py`
- `reports/evidence/ag01-demo/ag01-demo-transcript.txt`

## CLI

`uv run python scripts/agenda01.py --dsn <DSN> <subcommand>`; DSN also read
from `SETTLEMENT_TEST_DSN` (host-param form). Password DSNs are refused.
Subcommands: `init-db`, `propose`, `admit` (select_and_admit), `observe`
(record_outcome), `continue` (submit_continuation), `decline` (set_dormant
with typed wake condition), `answer`, `retire`, `wake` (process_wake),
`resume` (advance cursor / show resumable state), `explain` (agenda_snapshot
render: eligibility reasons, continuation basis, wake condition, costs,
outstanding liability; no SQL), `demo` (scripted journey, nonzero exit on
any invariant violation).

Transcript: `reports/evidence/ag01-demo/ag01-demo-transcript.txt` (exit 0,
49 lines). Journey: propose r1 -> stable-request replay (`already_applied`)
-> stale-revision refusal -> funded admit (exposure reserved, decision
charged) -> duplicate-slot refusal (no second effect) -> decisive outcome
linked (probe settled) -> useful continuation citing rc-1 (Q2, attempt B) ->
unknown outcome (exposure retained as liability) -> justified refusal citing
rc-2 -> dormant with `evidence-change:dep-seed` wake condition -> untyped
event ignored -> relevant `ev-dep-v4` reopens with a reason -> duplicate wake
deduped -> fresh-process `resume` via subprocess -> `explain` shows
decisions=3, probes_settled=4, outstanding_liability=2, budget_remaining=55,
cursor tick=3.

## Frozen-signature assumptions (contract change requests)

The STATE lane branch did not exist on origin at build time
(`git fetch origin codex/ag01-state`: no such ref), so merge-conformance is
coordinator-verified. The CLI resolves `settlement.agenda` functions by exact
name and calls them with these assumed shapes; confirm or correct at merge:

- `propose_option(dsn, cmd)`, `select_and_admit(dsn, cmd)`,
  `record_outcome(dsn, cmd)`, `submit_continuation(dsn, cmd)`,
  `set_dormant(dsn, cmd)`, `answer_option(dsn, cmd)`, `retire_option(dsn, cmd)`,
  `process_wake(dsn, cmd)`: all `(dsn, Command) -> CommandResult`, idempotent
  `request_id`, `ConflictPayload` on changed-payload reuse, `StaleRevision`
  where the contract names it. Payload keys are my proposal (see
  `StateBackend` in the script): `option_key/scope/question/revision/
  allocation_root/body`; `trajectory/option_id/probe/intended_decision/
  replication_slot/evidence_refs/dep_versions/cost`; `option_id/attempt_id/
  observation`; `option_id/parent_attempt/observation_refs/next_probe/
  residual_question/consequences/replication_slot/cost`;
  `option_id/expected_disposition_version/reason/wake_condition`;
  `option_id/event`.
- `explain_eligibility(dsn, option_id) -> dict` (read-only),
  `agenda_snapshot(dsn) -> dict` extended with eligibility reasons,
  continuation basis, wake condition, costs, outstanding liability.
- Request-id formats used: `ag01-propose-<key>-r<rev>`,
  `ag01-admit-<option>-<probe>`, `ag01-observe-<receipt>-<attempt>`,
  `ag01-cont-<option>-<probe>`, `ag01-decline/answer/retire-<option>`,
  `ag01-wake-<option>-<event>`.

Backend selection is explicit, never silent: `StateBackend` when all nine
functions resolve, else `DemoBackend`, and every invocation prints
`[backend] name=... note=...`.

## Checks + results

- `demo` on real PostgreSQL 16 (`agenda01_demo`, host-param DSN): exit 0,
  all 19 invariant checks held; rerun deterministic (reset-then-run).
- `uv run pytest tests/test_ag01_demo.py -q`: 4 passed in ~6s (full journey
  via subprocess incl. fresh-process resume leg, rerun, stale-decline
  refusal exit 2, wrong-attempt observe refusal, no-SQL-in-output assertion).
- New files only; `git status` shows no other modification, so the existing
  suite is unaffected by this lane (full suite runs at coordinator merge).
- No ruff binary in this environment; lines kept within 100 columns.

## Limitations

- `DemoBackend` is an explicit pre-merge stand-in, not the STATE accounting
  path: costs live in a demo-local 64-unit ledger (`demo_ag01_costs`), not
  real allocations; qualification is a demo-local subset of Q1/Q2/Q3
  (unknown/stale/settled/irrelevant refusals + Q1/Q2/Q3 admission routes);
  tables are `demo_ag01_*` so `migrations/0010_*` owns the real names
  without collision. Delete-or-keep is the coordinator's call after STATE
  merges; the CLI prefers `StateBackend` automatically once resolvable.
- Post-merge, `demo` against `StateBackend` needs a fresh trajectory DB for
  a green first run (fixed request ids replay `already_applied` afterwards).
- Fake providers/scratch ledgers here validate the operator surface only,
  not live inference or containment.
