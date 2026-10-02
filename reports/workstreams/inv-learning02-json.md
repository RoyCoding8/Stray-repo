# Inv-Learning 02 JSON workstream

## Assignment

Repair boolean JSON acquisition and harden the driver. Owned scope only:
experiments/ad01/live_construct.py, scripts/invl02_live.py,
tests/test_json_repair.py (new),
reports/workstreams/inv-learning02-json.md,
reports/evidence/invl02-json/, reports/jev/invl02-json-*.json.

Base verified: 4545a51 Handback: R1 R2 R3 closed with live E0 bound and
E12 incomplete. Branch wt/invl02-json. No merges. Nightjar commits.

## Task list

- Strict boolean extraction green on doubles.
- Fenced-block extraction green on doubles.
- Bounded repairs inside per-arm reserve green on doubles.
- Probe unknown usage stamping green.
- Recompute dispatch counting plus ceiling enforcement green.
- Guard success-cost versus ceiling refusal split green.
- Freeze micro-protocol before live effect.
- Rerun P1 P2 boolean acquisition only under frozen bounds.
- Jev narrow checkpoint with sanitized artifacts plus disposition.
- Report gates separately from live outcome. Drop scratch plus DB.

## Root cause

boolean_live_round sliced model text from the first left brace to the
last right brace and passed the substring to json.loads with no schema
check. JSON syntax failures escaped the repair counter and aborted the
arm. Structural leaks such as extra top-level keys and boolean const
values passed commit checks. The recorded P1 delimiter failure and P2
property-name failure are this path. Raw model bytes for those two
failures were not retained. Only the decoder diagnoses survive in
reports/evidence/invl02-r123/e12/e12-run.json. The failing tests use
same-class representatives that raise the same decoder errors through
the old path.

## Design

live_construct.py owns the boundary. extract_fenced_json takes the
first fenced block when fences exist and the stripped whole text
otherwise. Bare prose wrapped JSON is refused. The model prompt teaches
the fenced option. validate_boolean_payload requires exactly specs of
four entries with exact keys, integer const zero or one, integer mask
zero to fifteen, and null or listed pair indices. Boolean values are
rejected by type identity. extract_and_validate_boolean composes the
two and raises LiveRefused on any violation. Only its return enters an
arm record.

boolean_live_round routes transport, empty, schema, and commit failures
through one repair counter bounded by the frozen per-arm repair
allowance. Each failure appends its diagnosis to the next PRIOR FAILURE
prompt. Dispatches never exceed one plus repairs per boolean round.

LiveGuard splits cost refusal from ceiling refusal. is_cost_blocked
reports latched nonzero or billed usage. is_ceiling_reached reports
dispatch count against ceiling. infer refuses each through a distinct
kind. guard_status keeps cost_blocked and adds refusal_kind plus
ceiling_reached.

probe stamps usage on every outcome. Refused probes record unknown
usage. Error and text probes snapshot provider usage with unknown
preserved.

recompute counts claimed totals, ledger entries, and guard dispatches
separately. Ledger plus guard agreement against a divergent claim is a
dispatch miscount. Counted dispatches against the frozen model ceiling
is a ceiling exceed. Per-arm calls against init plus repair reserves
are checked when arms exist. Unknown usage stays unknown and is never
zero filled.

## Gate evidence

- tests/test_json_repair.py: 13 passed on doubles.
- Lane suites: test_r123_gates plus test_live_integration plus
  test_m4_offline_recompute plus test_m2_frontier_inherit green.
- Gate command: PYTHONPATH dot plus src plus experiments with uv run
  python minus m pytest.

## Live preflight

Probe responses 60000 returned probe text with 15 chars in 1.9 s.
Digest d91dc001 matches the prior route. Usage input 34 output 72
billed false charge zero. Guard dispatch one with refusal kind empty
and ceiling reached true at one of one. Protocols frozen under
reports/evidence/invl02-json before study effects. Freeze digest
ecfc915c with bounds 40 total, per-arm 17 init plus 3 repair, retries
3 per call.

## Live outcome

JSON rerun honest unavailable comparison under the frozen protocol.
Total 11 model calls under ceiling 40 with per-arm reserves 20 each.
P0 available with zero model calls and qual 1.0 via competent learner.
P1 unavailable after five calls with schema-invalid diagnosis
Expecting value line 1 column 1. P2 unavailable after six calls with
the same decoder class. No P1 outcome entered P2 inputs. Permitted
digest 04100922. Guard ledgers record every dispatch with usage.
Text outcomes carry stop reason length with output tokens at the 1024
cap and input tokens 331 to 552. Billed false with charge zero on all
text outcomes. No cost block. No ceiling refusal. Guard dispatches
match ledger entries per arm. Recompute passes with counted 11
against ceiling 40. Strict extraction did not flip availability. It
replaced delimiter and property failures with a uniform truncated
prose failure inside the repair budget.

Gates green on doubles are reported separately from this live outcome.
Live JSON proves bounded honest unavailable arms with preserved usage,
not a learning null.

## Jev narrow checkpoint

Request reports/jev/invl02-json-request.json. Response
reports/jev/invl02-json-response.json. Probabilities are evidence, not
authority. strict_changes_availability true probability 0.09.

Disposition: no availability change. Strict extraction keeps P1 P2
unavailable with a uniform schema diagnosis inside bounded repairs. It
does not restore model JSON emission. The next targeted change is a
compact prompt plus output budget that fits reasoning before the JSON
object, not a larger campaign. No code change follows from this
checkpoint alone.

## Remaining gaps

Model emits long reasoning prose and hits the 1024 output cap before
schema-valid JSON. Repairs lengthen the prompt without freeing output
budget. P1 P2 never reached the audit seed. E3 stays unavailable with
no eligible revised improver. Generality checkpoint still requires
cross-domain transfer beyond Boolean plus software.

## Exact commands plus SHAs

Base 4545a51. Protocol commit c814b49. Branch wt/invl02-json.
Freeze plus probe plus run plus recompute commands use set minus a
with the runtime env file outside Git and PYTHONPATH dot plus src
plus experiments. No secret values printed or stored. Disposable
database invl02_json on local socket, dropped after verification.
