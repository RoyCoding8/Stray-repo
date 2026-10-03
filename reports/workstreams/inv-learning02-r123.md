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

Superseded 2026-10-02. This section read "None." The review at
`reviews/INVESTIGATION-LEARNING-02-ACQUISITION-ASSESSMENT.md`, committed in
the same commit 2b007c2 that added this document, records two blocking
findings against the driver: that `run_e0` and `run_e12` turn
`acquisition.status == "retained"` into `revision.disposition == "bound"`, and
that `leaf_construct` labels an authored `_STRATEGY_SOURCE` menu member
`origin: "acquired"`. Both hold, as measured above. The disposition reading in
this document contradicted the review written beside it.

The fixed campaign calls, cross-arm history leak and narrow recompute named
below were present at the cited lines and are replaced by the paths above.

## Live outcome

The account this section originally carried is retained verbatim below under
"As recorded in 2b007c2". It was wrong on three points. The corrected reading
follows it, measured against the frozen record on 2026-10-02.

No model-acquired improvement was bound. `reports/evidence/invl02-r123/e0-run.json`
records the model's package as `"acquisition": {"status": "retained"}` and, in
the same file, `"revision": {"disposition": "bound", "release_id":
"acquired-live-live-r1"}`. Retained and bound are different states. The bound
digest `2af6f802...` never became the active package:
`frontier-live.json` carries `active_package.control_id = "acquired-high-r1"`
at digest `26e14402...`, and `lineage` holds only `eb1e11c3...` and
`26e14402...`. The bound digest appears in no lineage entry. The driver source
docstring now states the rule this record broke: E0 reports model bytes as
retained unless a post-restart child proves the same package bound.

The bound program cannot act. `acquired-live-live-r1.imp_source` is 66
characters:

    def STEP(view, state):
        return {"action": None, "state": state}

It compiles, so it passes the admission gate. `method_exec.verify_step_source`
(`method_exec.py:1281-1311`) parses the AST and checks arity, imports, dunder
access and forbidden calls; it never invokes the function and never inspects
the returned action. Executing it yields `{"action": None}`, which
`improve_channel.validate_improve_action` (`:1733-1735`) refuses with "improve
action must be an object". A program that provably cannot act was admitted and
recorded as `bound`.

The acquired arm holds authored bytes. `acquired-high-r1.imp_source` is
byte-identical to `IMPROVE_HIGH_SOURCE` in `improve_channel.py`, 1068
characters, sha256 `773875ae...` matching its recorded `imp_digest`. Its
`origin` field reads `"acquired"`. The driver asserted that authored controls
stay out of the acquired arms by comparing `package_digest`, and the authored
menu package differs from this descendant in `parent_digest` and `version`, so
the assertion passed while the bytes were the menu's. Neither treatment arm
carries a `source_kind` field, so the record cannot distinguish the two.

The frozen record is not reproducible from the committed source. Measured
2026-10-02 at `b1fca48`; the version and shape legs re-measured at `290d3a9`
and corrected below:
- `freeze.json` has no `protocol`, `run_id`, `route`, `route_digest` or
  `source_identity`. `_validate_live_freeze` (`invl02_live.py:428-435`) checks
  `protocol` first and refuses, so `run_e0` cannot have written this directory.
- `e0-run.json` lacks `status`, `route`, `route_digest`, `protocol`, `run_id`,
  `source_identity`, `study_root` and `durable_receipts`, all of which the
  driver writes. Re-measured 2026-10-02: that is **eight** missing keys, not
  seven, and the driver writes sixteen top-level keys to this file's nine.
- All three `frontier-*.json` stores declare `frontier_version:
  "invl02-frontier-v1"`. The committed `FRONTIER_VERSION` is
  `"invl02-frontier-v2"`, and loading any of them under committed code raises
  "uses an unknown frontier version". Measured 2026-10-02: all **five**
  stores under `invl02-r123/` are `-v1`, and the bump happened in the same
  commit that added them (see the correction below).
- The recorded `revision` mixes the bound shape (`disposition`, `release_id`)
  with the retained shape (`bound_digest`), and adds `construction_calls` and
  `reason: ""`. No function in `live_construct.py` returns that key set in any
  commit that touched the file. **Withdrawn 2026-10-02; see the correction
  below.** The two reasons the original list gave for this bullet were
  `reason: ""` and the v1 version, and both fail on measurement. The
  key-set observation itself stands.
- `frontier-live.json` `rounds[0].executed_digest` is `6bb3f351...` while
  `e0-run.json` reports `1251125b...` for the same round. **Withdrawn
  2026-10-02; see the correction below.**

Correction, 2026-10-02. The bullets marked withdrawn were reasoning errors,
not measurements, and the conclusion above is stronger without them because
three other markers are unchanged. Measured at `290d3a9`:

- The empty `reason` is not provenance evidence. `trajectory.py:1171`
  projected `episode.get("reason", "")` for **every** disposition. `bound` is
  the one disposition that legitimately carries no reason, so committed code
  produced exactly the archived shape. The `bound` branch of
  `live_construct.py:1328` emits no `reason` key, which is true and beside
  the point: the archived key set is a trajectory episode, not a
  `live_construct` return. `trajectory.py` has carried that projection line
  unchanged since `4e3c3bb`, the parent of the commit that added the archive.
- `6bb3f351...` is `IMPROVE_LOW_SOURCE` in `improve_channel.py`; `1251125b...`
  is `sha256(op_source)` of the active package. They are different channels
  (`IMPROVE` versus `OPERATE`) of different objects, not two reports of one
  round. `rounds[0].executed_digest` names the bytes that ran (the low
  incumbent); `rounds[0].candidate_id` names the bytes it produced
  (`acquired-high-r1`). `rounds[1].executed_digest` equals the run record's
  `second_executed` exactly.
- The `frontier_version` mismatch is still a real break, but not the one
  stated. `2b007c2` added the archive **and** bumped `FRONTIER_VERSION` from
  `-v1` to `-v2` in the same commit, so the committed loader cannot open a
  store the archive itself was added with. It is a schema-retirement
  mismatch, not a sign of a hand-written record.
- What does hold, and is the real provenance break: no commit has ever
  produced this record. `scripts/invl02_live.py` was added by the same
  commit that added the archive, and at that commit `run_e0` already wrote
  all sixteen top-level keys. This file has nine. The `revision` key set
  belongs to no function in the tree — `trajectory.py` emits `bound_digest`
  with `release_id` and `scope` and `binding`, never `construction_calls`
  beside a `bound` disposition, and `live_construct.py` never emits
  `construction_calls` at all. The one other projection, `records.py:392`,
  guards on `disposition in ("rejected", "unavailable")` and so returns
  `None` for a binding; only `trajectory.py:1171` can emit the empty reason.
- The three committed-driver assertions the archive violates are stronger
  than any shape argument. `invl02_live.py:1917` asserts
  `active.origin == "authored-control"`, `:1936` asserts the first candidate's
  `origin == "authored-control"`, and `:1937` asserts
  `source_kind == "fixed-menu"`. The archive records `active.origin ==
  "acquired"`, first candidate `origin == "acquired"`, and no `source_kind`
  field at all. A record satisfying the driver could not contain these bytes.
- The archive is internally genuine, which is why the shape arguments looked
  persuasive. Every `imp_digest` equals `sha256` of its own `imp_source`;
  both `freeze_digest` values recompute under the driver's own `_digest`
  (sorted keys, compact separators); the E0 record's `freeze_digest` equals
  `freeze.json`'s. The bytes were produced by something that really ran.

So the record is still not reproducible from committed code, on three
markers rather than five. The conclusion stands; two of its reasons do not.

What the record does support: one model dispatch reached the ledger with 84
characters of text and usage input 63 output 597 billed false, the package was
retained with a matching response digest, and E12 recorded honest unavailable
P1 and P2 arms. Those are retention and availability results. The
rounds recorded under `acquired-high-r1` and `acquired-high-r2` are runs of
authored bytes and are not model evidence.

### As recorded in 2b007c2

The following is what this document claimed when commit 2b007c2 added it. It
is kept as the record of what was believed, not as a statement of what
happened.

> E0 live bound from model bytes. Control frontier-control with zero model
> calls. Live frontier-live with one model call and one construction call
> under ceiling 12. Guard dispatch one with ledger text 84 chars and usage
> input 63 output 597 billed false charge zero. Revision bound with
> release acquired-live-live-r1. Observation dependence true with
> opp-first versus opp-followup. First round acquired-high-r1 adopted
> bound. Second round acquired-high-r2 after restart under inherited
> bytes. Authored controls out of acquired arms.


E12 incomplete comparison with honest unavailable arms. Total five model
calls under ceiling 80 with per-arm reserves 20 each. P0 available with
zero model calls and qual 1.0 plus audit 0.75 via competent learner.
P1 unavailable after two calls with JSON delimiter failure. P2
unavailable after three calls with JSON property failure. No P1 outcome
entered P2 inputs. Permitted digest 04100922. Control zero boundaries.

M4 export records six use records and twelve operations across four task
ids. `e12/m4-verify.json` reports `"status": "fail"` with 55 problems, not a
pass with zero problems. `e12/recompute.json` reports pass with zero problems;
the two disagree because the narrow E0 path and the full bundle verifier read
different files. Recomputed model five history zero failed five use six worst
56. Quality P0 1.0 with P1 P2 null. Comparison incomplete with missing P1 P2
and winner none. Accounting preserves unknown tokens plus child compute plus
billed unresolved. The 55 problems are the bundle's own accounting fields
declaring `measured: unknown` with no recomputable counterpart.

Gates green on doubles are reported separately from this live outcome, and
every acquisition assertion in `tests/test_r123_gates.py` and
`tests/test_invl02_causality.py` is a double: both use a scripted gateway, no
database and no network, and neither reads `reports/evidence/invl02-r123/`.

Corrected 2026-10-03 on integration. An earlier revision of this section
closed with "No test in the committed tree covers the archived record." That
was true at `b1fca48`, the base this lane measured on, and it is false at
`d421c58` and after. `tests/test_c8_gate_review.py` reads `e0-run.json` and
`frontier-live.json` directly and re-derives the bound digest, the response
digest and `reason == ""` from the archived bytes;
`tests/test_c5_executable_bound.py` reads the same live store. Both arrived in
`d421c58`. So the archive was not unguarded - it was guarded by tests written
against it as a specimen, which is the weaker of the two arrangements: they
pin the bytes reproduce, not that the run claim they decorate was ever
supported. `tests/test_c20_bound_record_claims.py` adds the missing half.

Live E0 proves model bytes reached retention and nothing further. Live E12
proves honest unavailable arms with no substitution, not a learning null.

## Jev integration checkpoint

The two cited artifacts do not exist in the committed tree. `reports/jev/`
is not a tracked directory and no file matching `invl02-r123-integration-*`
is present at `b1fca48`, so the three probabilities below have no retained
source. They are kept as the record of what was reported, not as evidence.

> Request reports/jev/invl02-r123-integration-request.json. Response
> reports/jev/invl02-r123-integration-response.json. Probabilities are
> evidence, not authority. r1_connected 0.77, r2_controlled 0.72,
> r3_verifiable 0.84.

> Disposition: no new concern requiring a code change. The three
> competing readings in the request are tested directly. Fixed order is
> refuted by choice_preserved versus choice_mismatch plus disconnect to
> stop. Prompt leakage is refuted by matched snapshots with P1 empty,
> P2 exactly permitted, plus refusal on swap or inject. Label trust is
> refuted by offline derivation of quality from canonical tables plus
> per-class tamper failures. Proceed to live E0 under the frozen
> protocol.

The label-trust refutation above does not hold. Label trust is exactly
what failed: an authored menu member reached `treatment_arms.acquired`
under `origin: "acquired"` with no `source_kind`, and the model's own
package was recorded `bound` while inert. Both are measured in the Live
outcome section.

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
