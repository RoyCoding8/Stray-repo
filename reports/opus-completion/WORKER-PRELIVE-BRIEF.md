# Worker brief: pre-launch hardening, exposure and spend

Repository `D:\AI\Agent-Society-v2-investigation-review`, branch
`codex/stage-09-opus-completion` at `eb52c8c`. Clean tree. Work in place.

You own exactly these files:

- `experiments/ad01/policy_step.py`
- `scripts/s09_pilot.py`
- `tests/test_s09o_prelive.py` (new)

Do not edit anything else. If another file must change, STOP and report what and why.

## Why

A mandatory pre-live-launch review scored two claims below 0.5 and the live study is blocked
until both are real rather than asserted.

`data_exposure_is_controlled` scored 0.35. `free_model_constraint_is_actually_enforced`
scored 0.41. Both are fair. Fix them.

## Gap 1: the policy view still carries unstripped task content

`policy_step.materialize_view` sets `"task_content": dict(task)`. An earlier fix projected
`observations` through `packet.project_observations`, but the task itself is still copied
raw. `packet.strip_task` exists and already removes `SEALED_KEYS` recursively plus
`access_label`.

With provider doubles this was harmless, and a test confirmed the specific frozen task
carried no sealed keys. With a real external provider on the other end the calculus is
different: an untrusted constructed policy reads its view and can compose a `request_model`
prompt from it, so unstripped task content becomes data sent to a third party.

Change `materialize_view` to pass the task through `packet.strip_task`. Keep everything else
about the view identical. `task_id` and `family` must survive, because the policy needs them
and existing tests assert them.

## Gap 2: the free-model constraint is described but not enforced

The live configuration promises a single pinned zero-cost model, no paid fallback, a 100
call aggregate ceiling with 2 already spent on discovery, and an abort if any response
reports a nonzero cost. None of that is implemented. It is currently a sentence in a report.

Implement it as a guard at the dispatch boundary in `scripts/s09_pilot.py`, wrapping the
real adapter that `_http_gateway` builds. Do not fork or reimplement
`settlement.gateway_http.HttpGatewayAdapter`; wrap it, delegate to it, and keep it the thing
that actually carries the bytes, because a separate preflight already proves the real
adapter is on the path.

The guard must:

1. Refuse before dispatching once a configured aggregate ceiling of study model calls is
   reached. Default the ceiling to 100 and accept an already-spent count, defaulting to 2.
   The refusal must be an explicit error, never a silent skip and never a fallback to a
   double.
2. Pin exactly one model id. If a request names any other model, refuse. This is what
   "changing provider or model mid-study is not authorized" means mechanically.
3. Inspect every response for a reported cost. The gateway returns it under
   `usage.cost` and `usage.market_cost`, and may also expose
   `providerMetadata.gateway.cost`. If any present cost field is nonzero, raise immediately
   and stop the study. A missing cost field must NOT be treated as zero; treat absent as
   unverified and refuse, so the check cannot be defeated by a response shape that omits it.
4. Count every dispatch attempt, including failures, empty responses and retries, because
   the cap sheet counts those.
5. Expose the running count and the reason for any refusal so the study report can record
   them.

Find the adapter's completion method by reading `src/settlement/gateway_http.py` and wrap
that exact method. Do not guess its name.

## Tests: tests/test_s09o_prelive.py

Own only database names beginning `s09o_prelive`. Never touch `ec02test_*`, `inv_*`,
`s09_local_*`, or any database you did not create. Make NO live model calls; use a
controlled local HTTP server and doubles only.

Required cases, each asserting literal expected values:

1. `materialize_view` given a task carrying a sealed key returns a view whose serialized
   form does not contain the sealed value, while `task_id` and `family` survive.
2. The guard refuses the dispatch that would exceed the ceiling, and the refusal names the
   ceiling. Assert the exact number of dispatches that did occur.
3. The guard refuses a request naming a model other than the pinned one.
4. The guard raises when a controlled response reports a nonzero `usage.cost`.
5. The guard raises when a controlled response omits every cost field, proving absent is
   treated as unverified rather than free.
6. The guard permits a controlled response reporting `usage.cost` of 0 and increments the
   count.
7. A failed dispatch still increments the count.
8. The guard delegates to the real `HttpGatewayAdapter` rather than replacing it. Assert
   this by observing that the wrapped adapter's own method was invoked against the
   controlled server.

## Verification you must run and report

```
wsl -d Ubuntu -u ubuntu -- bash /mnt/d/AI/s09o/gate.sh prelive tests/test_s09o_prelive.py
wsl -d Ubuntu -u ubuntu -- bash /mnt/d/AI/s09o/gate.sh prelive-regress tests/test_s09c1_continuity.py tests/test_s09c1_failure.py tests/test_s09c2a_actions.py tests/test_s09c2b_bind.py tests/test_s09c3_policy_pilot.py tests/test_s09m1_driver.py tests/test_s09m1_state.py tests/test_s09m2_construct.py tests/test_s09m2_policy.py tests/test_s09m34_bind.py tests/test_s09m34_cycle.py tests/test_s09m34_exposure.py tests/test_s09m34_visibility.py tests/test_s09m5_pilot.py tests/test_s09m6fix_bind.py tests/test_s09o_boundary.py tests/test_s09o_policy_assess.py tests/test_s09o_cycle.py tests/test_s09o_causal.py tests/test_s09o_export.py tests/test_s09o_integrity.py tests/test_s09o_pilot.py
```

The regression run currently stands at 133 passed, exit 0. It must stay at 133 passed. If
stripping the task breaks a test that asserted raw task content reached the policy, STOP and
report which test and what it asserted rather than editing it; that is a contract question
for the coordinator.

Report exact pass, fail, skip and error counts for both, plus a red result from before your
change for at least cases 1, 4 and 5. Let long runs finish; a stream timeout is not a
failure. Never report a count you did not observe.

## Style

No inline comments. Compact functions, data-driven repeated structure for the guard's
refusal table, no abstraction layer with a single caller. Match surrounding formatting.
