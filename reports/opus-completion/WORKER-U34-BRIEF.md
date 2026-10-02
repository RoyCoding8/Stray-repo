# Worker brief U3 and U4: connect assessment, binding and fresh-process continuation

Repository `D:\AI\Agent-Society-v2-investigation-review`, branch `codex/stage-09-opus-completion`,
at commit `f1ef179`. The tree is clean. Work in place.

You own exactly these files:

- `experiments/ad01/trajectory.py`
- `experiments/ad01/cli.py`
- `tests/test_s09o_cycle.py` (new)

Do not edit `policy_assess.py`, `policy_step.py`, `selection.py`, `records.py`,
`agenda_policy.py`, `construct.py` or any other file. If you believe one of them must
change, stop and report exactly what and why instead of editing it.

## The defect

The public revision path opens a proposal, constructs `learning-policy` `STEP` bytes and
freezes them, then stops with `assessment_status="pending"`
(`trajectory.py:711-761`, especially `734-753`). Nothing in production calls
`records.assess_frozen` or `selection.bind_revision`. The only callers are tests. So the
lifecycle is test-supplied, which the governing assignment forbids: "Do not call Stage 9
complete if policy assessment, exact activation, or fresh-process continuation is still
manually supplied by the tests."

Separately, `run_campaign` builds the legacy source-less `DecisionConsumer` whenever no
consumer is passed (`trajectory.py:464-481`, `804-825`), and `resume_campaign` only
forwards an optional consumer (`1236-1259`). No production path resolves a bound policy
from durable state, so a fresh process cannot continue under a revised policy unless a
test hands it one.

## What already exists. Use it, do not duplicate it

- `experiments/ad01/policy_assess.py` is a finished, tested policy-specific sealed
  assessor. Read it first, in full. It exposes `panel_for`, `rule_for`,
  `freeze_protocol`, `assess_policy`, `PANEL_PROTOCOL`, `EVALUATOR_VERSION`. Its 8 tests
  pass (`tests/test_s09o_policy_assess.py`).
- `selection.bind_revision` (`selection.py:62-214`) already validates exact frozen bytes,
  proposal protocol, assessment presence, the cited assessment attempt, assessment
  protocol, evaluator version, scope equality, the promoting outcome, a canonical request
  id, and atomic staleness with `SELECT FOR UPDATE`. Call it. Do not reimplement or
  weaken any of those checks.
- `records.load_freeze(dsn, proposal_id)` returns `{proposal_id, candidate_digest, entry,
  bytes, source}`. This is where the exact policy bytes already live durably.
- `selection.active_binding_for(dsn, family, release_id=...)` returns the release row.
  `selection.binding_provenance(binding)` returns `{proposal_id, candidate_digest}`.
- `policy_step.make_policy_artifact` and `policy_step.verify_policy_record`.
- `agenda_policy.step_policy_consumer(policy_record, dsn=..., cid=..., charter=...,
  world=..., arm=..., allocation_id=..., study_root=..., gateway=..., model=...,
  max_policy_steps=...)` builds the trusted STEP consumer. The `policy_record` it wants is
  the dict shape `policy_step.verify_policy_record` accepts: it needs `policy_source` plus
  the policy artifact fields.

## U3. Continue past freeze into assessment, then bind or reject

In `_construct_policy_revision`, after `records.freeze_candidate` returns, continue in the
same trusted path. Do not add a second loop or a new engine.

1. Build the panel with `policy_assess.panel_for(scope=scope, world=<the campaign world>,
   seed=proposal["proposal_id"])` and the rule with `policy_assess.rule_for()`.
2. Call `policy_assess.freeze_protocol(...)` BEFORE any assessment execution.
3. Resolve the incumbent policy bytes for the comparison. The incumbent is the policy the
   campaign is currently running under. Pass its exact source and artifact.
4. Call `policy_assess.assess_policy(...)`.
5. Verify the hinge: after `assess_policy` returns, `records.load_assessment(dsn,
   proposal_id, candidate_digest)` MUST return that assessment, because
   `selection.bind_revision` reads it through that function. Check this explicitly. If
   `policy_assess` journals under a request id that `records.load_assessment` cannot find,
   STOP and report it as a blocker rather than editing `policy_assess.py` or `records.py`.
6. Branch on `assessment["outcome"]`:
   - `"bind"`: call `selection.bind_revision` with the exact `proposal_id`,
     `candidate_digest`, `protocol_id`, `evaluator_version`, `scope`, and
     `evidence_refs=[assessment["attempt_id"]]`. Use `disposition="default"`. Pass
     `expected_versions` read from the current release row, so a concurrent replacement
     refuses rather than overwrites. Set the episode `disposition="bound"` and record the
     release id and the bound digest.
   - `"reject"`: create no release. Persist an explicit durable rejection through the
     journal. Set `disposition="rejected"`, `fallback="incumbent"`, and record the reason
     from the assessment. The incumbent stays active.
   - `"unavailable"`: create no release. Persist an explicit durable refusal. Set
     `disposition="unavailable"`, `fallback="incumbent"`, and record the reason. This case
     must stay distinct from `"rejected"` in the episode record.
7. A `StaleBind` from `bind_revision` is not a crash. Catch it, set
   `disposition="rejected"` with the staleness reason, and leave the incumbent active.
8. Charge every model call and query the assessment actually consumed into the campaign
   counters, the same way construction calls are charged at `trajectory.py:755-757`.
   Assessment cost must not be invisible.

## U4. Production resolves the bound policy, with no injected consumer

1. Add a keyword argument `policy_release: str | None = None` to `run_campaign` and to
   `resume_campaign`. `resume_campaign` must forward it.
2. Refuse ambiguous authority: if both `consumer` and `policy_release` are given, raise
   `ValueError`. A caller may supply a consumer, or name a release for production to
   resolve, never both.
3. When `consumer is None` and `policy_release` is set and `dsn` is not None, production
   resolves the policy itself:
   - `binding = selection.active_binding_for(dsn, family, release_id=policy_release)`.
     A `None` binding is an explicit refusal, not a silent fall back to the legacy
     consumer. Record the reason and stop with it.
   - `provenance = selection.binding_provenance(binding)`. Load
     `records.load_freeze(dsn, provenance["proposal_id"])`.
   - Refuse unless `freeze["candidate_digest"] == provenance["candidate_digest"]` and the
     SHA-256 of `freeze["source"]` equals that same digest. Exact bytes or nothing.
   - Build the policy record from those exact bytes with
     `policy_step.make_policy_artifact`, using the proposal's `parent_digest` and `scope`,
     and verify it with `policy_step.verify_policy_record`.
   - Build the consumer with `agenda_policy.step_policy_consumer(...)`.
4. When `policy_release` is None, behaviour must be byte-for-byte what it is today. 84
   existing tests depend on that. Do not change the default path.
5. `resume_campaign` with `policy_release` in a fresh process must resolve the same bytes
   and must not draw a new model call for an already-settled effect. The existing
   reconciliation at `trajectory.py:867-942` already does the settled-effect work; do not
   rewrite it.

## U7. One public lifecycle command

In `cli.py`, add a `cycle` subcommand that runs the whole thing through the public path:
acquire, check, retain and use a task method, incorporate feedback, revise, assess, bind
or reject, then continue. It must accept `--policy-release` and must NOT accept any way to
inject a consumer. Reuse the existing argument plumbing and the existing `run`/`resume`
helpers rather than adding a parallel command layer.

## Tests you must write: tests/test_s09o_cycle.py

Own only database names starting `s09o_cycle`. Create and drop only those. Never touch
`ec02test_*`, `inv_*`, or an `s09_*` database you did not create. Note that
`tests/test_ad01_traj.py` currently reports 5 errors from a missing `ec02test_adtr`
database owned by another task; that is pre-existing and not yours to fix.

Use a provider double for model responses. A test may supply model responses. A test must
NOT call `open_revision_proposal`, `freeze_candidate`, `assess_frozen`, `assess_policy`,
`freeze_protocol` or `bind_revision` itself. If your test has to call one of those to pass,
the production wiring is incomplete and that is the bug to fix.

Required cases, each asserting literal expected values:

1. Successful binding. One public `run_campaign` call produces an episode with
   `disposition == "bound"`, and afterwards `selection.active_binding_for` returns a
   release whose provenance digest equals the frozen candidate digest.
2. Rejected policy. A candidate that the frozen rule rejects leaves NO release, the
   episode says `"rejected"`, and the incumbent is still what a later decision runs under.
3. Unavailable constructor. The constructor returns bytes that are not a valid STEP source.
   The episode says `"unavailable"`, distinct from `"rejected"`, and no release exists.
4. Fresh-process continuation. After a successful bind, a SECOND OS process (use
   `subprocess.run` with a written probe script, as `tests/test_s09m34_cycle.py:159-184`
   does) calls `resume_campaign` with only the release id, and decides through the bound
   policy bytes. Assert the executed policy digest equals the bound candidate digest.
   The probe must not construct a consumer.
5. Interruption around an accepted effect. Kill between accepting an effect and recording
   it, then resume, and assert no second model request was drawn.
6. Receipt reuse at exhausted allowance. With the model allowance spent, resume reuses the
   settled receipt and draws no new model call.
7. Disconnect. With the gateway unavailable, the cycle records an explicit durable refusal
   rather than a silent stop.
8. Both domains. Run case 1 for the software family and for the graph family.

## Verification you must run and report

```
wsl -d Ubuntu -u ubuntu -- bash /mnt/d/AI/s09o/gate.sh u34-cycle tests/test_s09o_cycle.py
wsl -d Ubuntu -u ubuntu -- bash /mnt/d/AI/s09o/gate.sh u34-regress tests/test_s09c1_continuity.py tests/test_s09c1_failure.py tests/test_s09c2a_actions.py tests/test_s09c2b_bind.py tests/test_s09c3_policy_pilot.py tests/test_s09m1_driver.py tests/test_s09m1_state.py tests/test_s09m2_construct.py tests/test_s09m2_policy.py tests/test_s09m34_bind.py tests/test_s09m34_cycle.py tests/test_s09m34_exposure.py tests/test_s09m34_visibility.py tests/test_s09m5_pilot.py tests/test_s09m6fix_bind.py tests/test_s09o_boundary.py tests/test_s09o_policy_assess.py
```

That harness pins `PYTHONPATH` and writes to `/mnt/d/AI/s09o/logs/<name>.log`. The second
command takes roughly 11 minutes. Let it finish; a stream timeout is not a failure. Report
the exact pass, fail, skip and error counts from both, plus a red result from before your
change for at least cases 1, 2 and 4.

The regression run must keep all 84 pre-existing Stage 9 tests passing plus the 11 newer
ones. If any previously passing test now fails, fix your change. Do not invert an
assertion, do not weaken a runtime check, and do not delete a test to get green. If a
fixture genuinely must migrate, say which contract changed and preserve the old test's
purpose.

## Style

No inline comments. Compact functions, data-driven repeated structure, no abstraction layer
with a single caller. Match surrounding formatting. Keep untrusted policy and candidate code
in bounded child execution; nothing untrusted runs in the host process.
