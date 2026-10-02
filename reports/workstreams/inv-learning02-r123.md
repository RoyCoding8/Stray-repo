# Inv-Learning 02 R123 workstream

## Assignment

Close IL02-R1 R2 R3 with behavioral checks while the pinned free route
is unavailable. Challenge findings with source evidence and record
disagreements with file line references. Owned scope only:
scripts/invl02_live.py, experiments/ad01/live_construct.py,
tests/test_live_integration.py, tests/test_r123_gates.py (new),
reports/workstreams/inv-learning02-r123.md,
reports/evidence/invl02-r123/, reports/jev/invl02-r123-*.json.

Base verified: 4027814 Review Investigation Learning 02 live path and
comparison gates. Branch wt/invl02-r123. No merges. Nightjar commits.

## Task list

- R1 durable investigation path green on doubles.
- R2 matched P1 P2 with P0 and crosstalk refusal green on doubles.
- R3 M4 bundle export plus offline verify plus per-class tamper green.
- Response-byte preflight with runtime env file, no secret prints.
- Freeze E0 plus E12 protocols before study effects.
- Commit protocol before E0. Run E0, on success E1 E2 under grant bounds.
- M4 export plus verify plus recompute over live bundle.
- Jev integration checkpoint with sanitized artifacts plus disposition.
- Report gates separately from live outcome. Drop scratch plus DB.

## R1 design

live_construct.py owns the durable path. live_mission plus
ensure_live_store plus propose_live_work plus bind_live_control plus
choose_next_work plus execute_chosen_work plus run_live_improve_round
plus build_live_package plus parse_and_build_live_package plus
adopt_live_revision plus restart_store plus live_frontier_round.
Operate and improve STEP bytes run via improve_channel through
method_exec.run_step_out_of_process. That is the public child path.
Effects run via improve_channel.execute_operate_action. Authored
controls stay labeled authored-control. retain_acquired plus
adopt_live_revision refuse authored packages. Treatment arms hold only
acquired digests.

invl02_live.py routes E0 and E12 through _run_frontier_investigation.
_run_campaign plus _consumer_for plus _apparatus_record plus _subdivide
deleted. E0 control uses frontier with no guard. E0 live uses frontier
with LiveGuard for one live improver acquisition. E12 arms use per-arm
frontier stores with per-arm guards. Observation dependence recorded as
choice_preserved versus choice_mismatch. Restart proved by reload plus
round two under inherited bytes with executed digest equality.

Counterchecks: disconnect frontier changes investigate to stop or is
refused. Disconnect improvement with non-STEP bytes is refused. Swap
low versus high changes probe x 3 versus 11.

## R2 design

_permitted_dev_history builds development history deterministically via
VersionSpaceLearner on dev seeds, no model calls. _arm_snapshot pins
identical solver seed plus class digest plus empty archive plus model
plus budget, differing only in history. P1 history is empty. P2 history
is exactly permitted. _validate_arm_histories refuses P1 non-empty, P2
not equal permitted, and P1 digest inside P2 inputs. _run_p0_boolean
evaluates the competent VersionSpaceLearner on the same held-out qual
plus audit seeds with zero model calls. boolean_live_round returns
failed_attempts plus history_tokens plus predictor specs plus tables
plus target tables. run_e12 runs P1 P2 on the same held-out qual 11
plus audit 23 with separate guards and reserved ceilings. Order cannot
starve an arm. Final pair validation runs after both arms. Old
cross-arm history accumulation removed.

## R3 design

export_m4_bundle builds the M4 verifier bundle from freeze plus e12
run plus arm booleans. Tasks map boolean held-out targets to canonical
tables. Quality derives offline as observed canonical predictor tables
versus expected canonical target tables. Candidate identity derives
from predictor specs plus permitted digest. Arm availability maps
available versus unavailable with reasons. Accounting recounts model
dispatches plus tool queries plus unresolved exposure. Tokens plus
child compute plus billed units stay unknown with declared sources.
Billing unresolved stays unknown, never zero. verify_m4_bundle runs
offline_recompute.verify_bundle with no gateway, database, or secrets.
recompute routes to verify_bundle when m4-bundle.json exists. Narrow
checks remain labeled E0-only when no M4 bundle exists.

Tamper classes: identity, content, membership, costs, results. Each
fails with a distinct problem.

## Gate evidence

- tests/test_r123_gates.py: 18 passed on doubles.
- tests/test_live_integration.py plus test_m4_offline_recompute.py plus
  test_m2_frontier_inherit.py: 42 passed.
- Gate command: PYTHONPATH dot plus src plus experiments with the repo
  venv python minus m pytest tests/test_r123_gates.py minus q.
- Integration command: same PYTHONPATH with tests/test_live_integration.py
  tests/test_m4_offline_recompute.py tests/test_m2_frontier_inherit.py.
- Driver source contains _run_frontier_investigation in run_e0 and run_e12
  with no _run_campaign. E12 contains _permitted_dev_history plus
  _run_p0_boolean plus _validate_arm_histories plus _arm_snapshot with no
  cross-arm accumulation.

## Live preflight

Probe responses 60000 returned probe text with 15 chars in 1.2 s.
Route serves response bytes. Frozen E0 digest 4db4625b. Frozen E12
digest 1b833d68. Both match the prior frozen bounds. Protocols frozen
under reports/evidence/invl02-r123/ plus e12 before study effects.

## Disagreements

None. The live assessment R1 R2 R3 findings match the driver source.
Fixed campaign calls, cross-arm history leak, and narrow recompute were
present at the cited lines and are replaced by the paths above.

## Live outcome

E0 live bound from model bytes. Control frontier-control with zero model
calls. Live frontier-live with one model call and one construction call
under ceiling 12. Guard dispatch one with ledger text 84 chars and usage
input 63 output 597 billed false charge zero. Revision bound with
release acquired-live-live-r1. Observation dependence true with
opp-first versus opp-followup. First round acquired-high-r1 adopted
bound. Second round acquired-high-r2 after restart under inherited
bytes. Authored controls out of acquired arms.

E12 incomplete comparison with honest unavailable arms. Total five model
calls under ceiling 80 with per-arm reserves 20 each. P0 available with
zero model calls and qual 1.0 plus audit 0.75 via competent learner.
P1 unavailable after two calls with JSON delimiter failure. P2
unavailable after three calls with JSON property failure. No P1 outcome
entered P2 inputs. Permitted digest 04100922. Control zero boundaries.

M4 export tasks four records six. Verify pass with zero problems.
Recomputed model five history zero failed five use six worst 56.
Quality P0 1.0 assess with P1 P2 none. Comparison incomplete with
missing P1 P2 and winner none. Accounting preserves unknown tokens plus
child compute plus billed unresolved. Recompute routes to
offline_recompute.verify_bundle for E12 and stays E0-only narrow for
E0. Both recomputes pass.

Gates green on doubles are reported separately from this live outcome.
Live E0 proves a connected trajectory. Live E12 proves honest
unavailable arms with no substitution, not a learning null.

## Jev integration checkpoint

Request reports/jev/invl02-r123-integration-request.json. Response
reports/jev/invl02-r123-integration-response.json. Probabilities are
evidence, not authority. r1_connected 0.77, r2_controlled 0.72,
r3_verifiable 0.84.

Disposition: no new concern requiring a code change. The three
competing readings in the request are tested directly. Fixed order is
refuted by choice_preserved versus choice_mismatch plus disconnect to
stop. Prompt leakage is refuted by matched snapshots with P1 empty,
P2 exactly permitted, plus refusal on swap or inject. Label trust is
refuted by offline derivation of quality from canonical tables plus
per-class tamper failures. Proceed to live E0 under the frozen
protocol.

## Remaining gaps

P1 P2 boolean predictor JSON remains malformed. The model served bytes
but not valid specs JSON after two repairs. Next targeted repair is a
strict boolean prompt schema plus a fenced JSON extractor within the
reserved repair budget, not a larger factorial campaign. E3 stays
unavailable with no eligible revised improver. Generality checkpoint
still requires cross-domain transfer beyond Boolean plus software.

## Exact commands plus SHAs

Base 4027814. Protocol commit 0108168. Live commit pending push of this
report plus evidence plus the E12 digest fix. Branch wt/invl02-r123.
Probe plus freeze plus run plus export plus verify plus recompute
commands use set minus a with the runtime env file outside Git and
PYTHONPATH dot plus src plus experiments. No secret values printed or
stored. Disposable database invl02_r123 on local socket, dropped after
verification.
