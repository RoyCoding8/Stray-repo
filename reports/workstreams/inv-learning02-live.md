# Workstream inv-learning02-live: bounded live qualification

Lane branch `wt/invl02-live`, base `5cb60ac`, integration update `11472ec`.
Owned paths only. Frozen pilot, trajectory internals, M0-M4 components untouched.

## Gates

- `PYTHONPATH=.:experiments uv run --with pytest python -m pytest tests/test_s09m5_pilot.py -q` → 8 passed.
- Same prefix over `tests/test_ad01_traj.py tests/test_s09c3_policy_pilot.py tests/test_s09o_pilot.py` → 46 passed.
- Same prefix over `tests/test_m1_shared_executor.py tests/test_m2_frontier_inherit.py tests/test_m3_rule_instrument.py tests/test_m4_offline_recompute.py` → 55 passed.

## Runtime

Environment file outside Git supplies gateway endpoint and key, grant
identifiers, model identifier and study spend counter. Disposable database
`invl02_live` on the local socket answers. Gateway model list contains the
requested model identifier. No secret values in Git, prompts, reports,
fixtures or evidence.

## Design

`experiments/ad01/live_construct.py` owns the live boundary. A counting
guard pins the model, refuses over-ceiling dispatch before sending, retries
at most 3 times per call, blocks later calls on observed nonzero cost, and
records usage and cost fields honestly with unknown staying unknown. It
deviates from `StudyGatewayGuard` in one recorded way. Absent cost fields
record unknown instead of refusing, because the local gateway reports usage
with zero charge units rather than priced cost fields.

Construction reuses `construct.construct_method` and
`construct.construct_policy` through broker model-inference operations.
Parsing reuses `packet.parse_construction_response`. Checking reuses
`method_exec` out-of-process child execution. Retention writes acquired
bytes into the frontier store treatment arms with origin `acquired`.
`improve_channel.leaf_construct` from strategy source stays a labeled
control and never enters treatment arms.

`scripts/invl02_live.py` drives E0, E1/E2 and E3 through
`trajectory.run_campaign` and `trajectory.run_use`, with assessment through
the shared dispatcher and independent scoring. `recompute` re-derives
digests, qualities and totals from the committed bundle alone.

## Jev

- Integration checkpoint before panels. `live_route_real` 0.4 is an
  accepted concern. The driver answers it with a digest chain plus a tamper
  probe. `control_separation` 0.76 is accepted with no change.
- Study checkpoint after panels. `diagnosis_sound` 0.68 and `stop_correct`
  0.76 are accepted as supporting evidence, not verdicts. The upstream
  diagnosis stays an inference a later byte-acquiring rerun would
  supersede.

## Studies

E0 protocol frozen in `reports/evidence/invl02-live/freeze.json` before
the first live effect. At most 12 model calls with 2 repairs. E1/E2
protocol frozen before its first effect. At most 80 total with per-arm
reserve 20 and 2 repairs each. Retries at most 3 per call.

## E0 outcome: acquisition failed at transport, panels stopped

Live construction reached the broker and dispatched, but the upstream
route served no response bytes. Four attempts on the first construction
call (init plus 3 frozen retries) each ended in transport timeout. Three
bounded diagnostic probes then discriminated the cause. A tiny prompt at
60s patience timed out at exactly 60.1s. The same prompt at 300s patience
received HTTP 502 after 180.1s. The chat API at 180s patience received
HTTP 502 after 180.1s. Both serving APIs fail for the pinned model. The
gateway itself answers health and discovery. This is an upstream capacity
or routing failure, not client patience and not a model inability claim.
No response bytes means no acquisition and no qualification verdict.

Live usage for E0. Seven dispatches against the ceiling of 12. Four
construction attempts plus three diagnostic probes. Zero text responses.
Zero observed cost. Usage stays unknown on every error entry. Billing
stays unknown, never zero.

The apparatus control ran clean through the same campaign path with zero
model calls and one settled boundary. E1/E2 did not run because the
preflight did not permit. Its protocol is frozen in
`reports/evidence/invl02-live/e12/freeze.json` and not executed. E3 is
unavailable because no revised improver was ever acquired. The exact
rerun command is `set -a plus source of the environment file plus set
plus a, then PYTHONPATH dot plus experiments uv run python
scripts/invl02_live.py run-e0 --dsn with the disposable database --out
reports/evidence/invl02-live`.

Recompute over the committed E0 bundle passes with zero problems. The
trust statement in `recompute.json` holds. Re-execution witnesses
behavior while record rewriting does not.
