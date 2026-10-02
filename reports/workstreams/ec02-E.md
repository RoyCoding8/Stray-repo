# EC02 lane E report — early contracts (EC02)

Base `d9795b6`, integration tip `d02e69a`, merge commit `7ec26a1`.
Branch `ec02-lane-E`. DB `ec02test_e` (host `/var/run/postgresql`,
user `ubuntu`).

Scope: early contract work only (EC02). Shared trial/record schema,
cost-union helper, freeze-assembly helper, promising rule as a pure
function, live-grant preflight gate, contract-level tests. The full
four-arm entry starts after R/W/L land; no live panels were run.

## What was built (`experiments/coord02/`)

- `schemas_evidence.py` (new, lane E owned): shared trial/record
  schema both L-construction output and E-evidence consume;
  cost-union reconciliation; freeze-contents assembly; promising
  rule. Reuses lane R seams only by confirmation (outcome/liability
  shape, `(freeze, panel, task, repeat, arm)` identity,
  `coord02-experience/1` packet) and lane W helpers directly
  (`freeze.build_freeze`/`verify_freeze`, `checker.make_record`/
  `check_evidence`, `oracle.task_input_digest`); nothing duplicated.
- `preflight.py` (new, lane E owned): live-grant preflight gate.

Trial record (`coord02-trial/1`): identity freeze/panel/task/repeat/
arm; provenance source-SHA/config-digest/package-digest/freeze-id;
outcome success/failure/refusal/timeout/incomplete; solved flag;
protected passed/failed/total with quoted failures; cost-union fields
model tokens in+out/calls, source-tool invocations, sandbox ops
(incl. policy-exec + protected-check subset ops), CPU-wall/elapsed/
abandoned; operations list (operation_id + kind, deduped);
liabilities with party/reason; internal accounting; external billing
with unknown-not-zero. Refusal/timeout/incomplete carry zero success
by construction with costs kept.

Cost-union reconciliation: operation-identity unions over builds,
validation, episodes, failed and cancelled ops; duplicate ids merge
only when kind+costs agree, conflicts raise; unknown nullable costs
propagate as unknown, never zero.

Freeze assembly: package bytes digest, input contract, exposure
manifest (must reference the frozen bytes), selector, baselines
declared BEFORE inspecting the acquired package (enforced), model/
config; delegates to `freeze.build_freeze` so schedule/budgets/rules
stay lane W's single source of truth.

Promising rule (pure function, design section 11): L vs S, A, F
independently on evaluation (family cap 1) + transfer (cap 0);
strictly-more with each resource <=1.25x, or tie with no increase
and strictly fewer model tokens; zero denominator permits only zero
numerator; unknown mandatory totals return unevaluable. `promising`
requires all three comparators on both panels; raw vectors returned
even on failure.

Preflight gate: refuses live panels without gateway endpoint +
model/API/key + finite grant declaration
(`EC02_LIVE_GRANT_EPISODES` covering the requested cells);
`require_live` raises `PermissionError` with the exact blocked
command.

## Gate

`tests/test_coord02_experiment.py`: 26 passed on real PG
(`ec02test_e`) + real subprocesses (via `checker.make_record` /
oracle evaluation), no model calls. Covers schema round-trip,
identity/outcome/cost/billing validation, checker bridge,
freeze-assembly incl. both refusal cases, union dedup/conflict/
unknown/kind-coverage, promising unit vectors incl. refusal/
unknown/zero-denominator/family-cap/joint cases, preflight
refuse/under-granted/admit, DB union vs naive double-count,
freeze anchor round-trip, checker DB cross-check, no-grant guard.
R+W lanes unaffected: `test_coord02_runtime.py` +
`test_coord02_workload.py` 30 passed, 2 skipped (pre-existing
`SETTLEMENT_TEST_DSN`-gated skips, unrelated).

## Blocked live command

No grant exists in this environment (no `TEAM01_LIVE_API_KEY`;
unauthenticated inference rejected). `preflight_live()` returns
admitted False with remaining cells evaluation 96 + transfer 48.
Exact blocked command:

`TEAM01_LIVE_API_KEY=<grant> EC02_LIVE_GRANT_EPISODES=<n> SETTLEMENT_GATEWAY_ENDPOINT=<endpoint> uv run python -m experiments.coord02.entry --panel <evaluation|transfer> --model <model>`

Full panels (96+48+12) await the human's grant.

## Full entry (commit `905213b`, branch `ec02-lane-E`)

`experiments/coord02/entry.py` (437 lines after slop-reduction from
557): one shared execution path for all four arms through the lane R
controller (`dev_constructor` constructors, never lane-local worker
logic). Task-stamped policy scripts emit valid `single` (S/A) /
`decompose` (F) plans; L executes the acquired package entry bytes
(doubled dev runs fall back to the S policy bytes inside `run_cell`,
explicitly marked as the doubled stand-in).
Evidence restages the assembled candidate tree from team tables
(launch snapshot + child outputs), re-grades protected cases with the
oracle, and writes checker-clean records under the canonical freeze
(`freeze_mod.write_freeze`, no scoped-freeze fork). Live panels
refuse without the grant via `preflight.require_live` (exit 2).

Bugs found and fixed at the root during construction: policy-script
SyntaxError (conditional expression outside a call); `plan` shape
names outside team SHAPES; child input-binding admission; 0/0/0
protected tally on ungradable cells contradicting the
schema+checker joint contract (failed trials carry exactly the
failed protected quotes).

Gate: `tests/test_coord02_experiment.py` 31 passed on real PG
(`ec02test_e`), including the doubled 96-cell development round
trip (12 tasks x 2 repeats x 4 arms) with checker-clean evidence
and a clean `status_view`.

## Limits

- Doubled development cells only; evaluation/transfer panels need
  the live grant (preflight refuses; exact blocked command above).
- R2/R3 confirmations recorded: outcome/liability shape and pair
  identity match `reports/workstreams/ec02-R.md`; packet fields map
  to cost-union inputs via `from_checker_record` + trial costs.
- Decisions for `reports/DECISIONS.md` ingestion: trial version
  `coord02-trial/1`; ratio 5/4 integer math; nullable CPU/wall/
  elapsed; grant env names `EC02_LIVE_GRANT_EPISODES` /
  `EC02_LIVE_GRANT_CALLS`.
