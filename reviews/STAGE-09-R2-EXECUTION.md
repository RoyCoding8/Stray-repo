# Stage 09 R2 challenger: execution, provenance and visibility

Read-only review at `dd504e1` on branch `wt/r2-execution`. Nothing in the repository was modified. Every runtime claim below was executed in this worktree with the project interpreter `/home/ubuntu/AI/Agent-Society-v2/.venv/bin/python`. No live model call, no database create or drop, no router restart.

The file the handoff sent me to read is `WORKER-STAGE-09-CONNECTED-STUDY.md`, whose CS-02 names two things. I verified both and found that one is fixed at the tip, one is not, and one more unpinned live path in a different script has the identical defect the handoff did not name.

---

## 1. Independent verdict on CS-02

**The route half is fixed. The exit-0 half is not. The causality half is not.**

### 1.1 The gateway refusal is real and by design. CONFIRMED

`src/settlement/gateway_http.py:703-710`:

```python
def _pre_dispatch_route_error(self, request: ModelRequest) -> GatewayError | None:
    if self.expected_route is None:
        if self.route_mode == "paid":
            return None
        return _error(
            GatewayErrorKind.PROTOCOL, "expected free route is required", False,
            request.operation_id, route_error=GatewayRouteError.EXPECTED_ROUTE,
        )
```

Measured, at the tip, with a default-constructed adapter:

```
s09_pilot live adapter pre-dispatch: GatewayError
   message: expected free route is required
   route_error: GatewayRouteError.EXPECTED_ROUTE
   response_received: False
constructor default expected_route: None
constructor default route_mode: free
```

The adapter is right. An endpoint does not establish a tier, so refusing an unpinned dispatch is the correct default. Nothing here is a bug in `gateway_http.py`.

### 1.2 The study fix is present. CONFIRMED

`scripts/inv01_study.py:804-836` reads `SETTLEMENT_EXPECTED_ROUTE`, refuses a non-free tier, refuses a model mismatch, and `:856-859` refuses a live provider with `route is None`. `run_study_v1` calls `_v1_route_from_env(model)` at `:953-957` and returns 2 before `out.mkdir`. `tests/test_inv_r1_live_route_pin.py` covers the adapter and the contract shape.

The commit that added it is `362f696`, "Refuse a live study that cannot name the route it would spend on". So the specific study CS-02 describes no longer spends nothing silently.

### 1.3 The exit-0 half survives the fix. CONFIRMED. Severity high.

A refusal anywhere below the study entry still produces exit 0 with nothing done. I traced and executed the whole path.

The study-level refusal is now the only refusal that changes the exit code. Everything downstream is absorbed.

`experiments/ad01/agenda_policy.py:205-218` catches every exception from the proposer, journals a correction, and after `MAX_CORRECTIONS = 2` (`:17`) returns:

```
consumer outcome: {"corrections": 2,
  "reason": "admission refused after 2 bounded correction(s): learner call
  ad01-x-learner-0 left no settled response",
  "status": "refused"}
```

`experiments/ad01/trajectory.py:548-554` turns that refusal into an ordinary episode:

```python
if outcome.get("status") == "refused":
    episode = {"disposition": "no-candidate",
               "fallback": "incumbent",
               "fallback_reason": outcome.get("reason", "refused"),
               "task_id": task_id, "queries": 0}
    return seed_obs, episode, 0
```

I ran `_run_boundary` with a proposer that raises exactly what `learner.model_propose` raises when the gateway refuses every dispatch:

```
observation verdict: unmeasured
episode disposition: no-candidate
fallback: incumbent
fallback_reason: admission refused after 2 bounded correction(s): learner call
  ad01-x-learner-0 left no settled response
spend (witness queries): 0

=> no exception.
```

Then `run_campaign` returns a well-formed campaign with `boundaries` populated, `stop.reason` "no admissible work remains", and `model_calls: 0`. `run_study_v1` appends it to `trajectories`, writes `study.json`, `accounting.json`, `manifest.json`, `freeze.json`, and `return 0` at `scripts/inv01_study.py:1184`.

So the exit-0 path is not the one the fix touched. The fix moved one refusal to the entry and left every other refusal silent.

### 1.4 The causal half of CS-02 is unfixed. CONFIRMED. Severity high.

`s09_study_preflight.collect` at `experiments/ad01/s09_study_preflight.py:1233` still reads use records out of the bundle the study is about to write:

```python
governance = probe_policy_execution(read_bundle(config.bundle))
```

I exercised `probe_policy_execution` directly.

| input | verdict |
| --- | --- |
| the committed `evidence_s09_m3_live/use_records.json` (24 records) | `Unmeasured` |
| two records where `executed` is `incumbent`, `executed_policy_digests` is a nonempty list of two backfilled digests, and `policy_actions` is a nonempty list | **`Pass`** |
| the same two records with `executed: "unavailable"` | `Unmeasured` |

The forged input is a bundle in which **nothing ran**, and the probe returns `Pass`, which makes `Preconditions.may_start` (`:283-292`) true. The handoff's own words are right that the predicate is not causal. Two specifics make it worse than the handoff says.

First, the two checks are on **different records**. `with_digests` (`:1111-1113`) and `with_actions` (`:1119-1120`) are independent comprehensions over `executed` / `with_digests` respectively, and `distinct` (`:1126-1127`) iterates `with_digests` and ignores `with_actions` entirely. Record A can carry the digests and record B the actions, and the summary at `:1133-1138` then reports "N of M executed use records carry X and Y" as though one record carried both.

Second, digest diversity is a *harm*. The handoff says a valid single retained policy need not change digest between tasks. It is worse than that: a correct run of one retained policy across several use tasks is **guaranteed** to fail this gate, because `distinct` counts tuples across records and one policy yields one tuple. The gate rewards an inconsistency (the same policy reported under two digests) and punishes the consistent case.

### 1.5 A second unpinned live path, same defect. CONFIRMED. Severity high.

`scripts/s09_pilot.py:1091-1096`:

```python
if gateway is None and gateway_mode == "live":
    from settlement.config import Settings
    from settlement.gateway_http import HttpGatewayAdapter
    gateway = HttpGatewayAdapter.from_settings(
        Settings.from_env(), api="responses")
    _guard_http_gateway(gateway)
```

`from_settings` passes `expected_route=None` and leaves `route_mode` at its constructor default of `"free"`. Measured, at the tip: the adapter refuses every dispatch with `expected free route is required`. So `s09_pilot.py run --mode live` cannot have dispatched anything, ever, since this line was written.

The guard wrapped around it cannot see it. `scripts/s09_pilot.py:216-242`, `StudyGatewayGuard.infer`:

```python
response = self.delegate.infer(request)
captured = self._captured()
...
if isinstance(response, GatewayError):
    self._check_incurred_cost(response, captured)
    return response
```

A `GatewayError` is returned unchanged. The guard's cost check only ever runs on a response, and a refusal is not a response. The guard has no notion of "this dispatch never left the client."

`experiments/ad01/live_construct.py:289-304`, `LiveGuard._route_failure`, has the same hole. I measured it:

```
LiveGuard._route_failure with expected_route=None: None
```

`expected_route is None` returns `None`, meaning "no route failure", and `_route_failure` is the only thing that would have turned a returned `GatewayError` into a `LiveRefused`. The INVL02 guard accepts a route that was never pinned.

One more inconsistency in the same file, worth naming because it is the reason this is not caught. `scripts/s09_pilot.py:699-708`, `_http_gateway`, the *controlled* path:

```python
adapter = HttpGatewayAdapter(
    endpoint=endpoint, api="responses", route_mode="paid",
    client=_CostCapturingClient(costs))
```

`route_mode="paid"` with no pinned route dispatches freely. So the same script has one live path that can never dispatch and one controlled path that always dispatches, and the only difference is a string.

`_assert_gateway_preflight` (`:929-936`) runs for both `controlled` and `live` and checks only the class, the api and the endpoint. It does not check the route.

---

## 2. What makes a live run exit 0 having done nothing

The general rule, stated once:

> **A run exits 0 when no exception escapes. Every refusal below the process entry is converted into a well-formed value, and the caller has no zero-effect check.**

The chain has four links, each verified.

**Link 1, the gateway refuses before send.** `gateway_http.py:703-710`. This produces a `GatewayError` with `route_error` set, `response_received` False.

**Link 2, the broker settles it as a durable receipt.** `src/settlement/broker.py:574-595`, `_model_error_receipt`:

```python
if route_error is not None and not response_received:
    response_class = "pre-send-route-refusal"
    outcome = "failure"
    actual_cost = 0
    sent = False
```

`_record_model_receipt` (`:625-638`) admits it, delivers it and returns `_status_of(...)`. `dispatch_operation` returns a `DispatchStatus` that no caller inspects for effect. The operation is now permanently settled. Re-dispatching it will hit `_decided_receipt` at `:516` and park.

**Link 3, the consumer absorbs the failure.** `agenda_policy.py:205-218` turns the "no settled response" into a correction, and after two corrections a refusal. `trajectory.py:548-554` turns the refusal into `disposition: "no-candidate"`, `fallback: "incumbent"`, `spend: 0`.

**Link 4, the study reports success.** `run_campaign` returns a campaign dict with a populated `boundaries` list. `scripts/inv01_study.py:1059-1064` appends it to `trajectories` with `model_calls` and `construction_calls` read off the campaign. The only aggregate check is `:1144-1148`:

```python
if totals["model_calls"] > 360 or totals["construction_calls"] > 24:
```

A ceiling. A run that spent zero is under every ceiling.

The consequence is that **the two guarantees are exactly opposed to each other**. The `_settled_text` short circuit, which `experiments/ad01/s09_doubles_forensics.py:210-212` correctly identifies as the load-bearing provenance property, is also the mechanism by which a spent-nothing run cannot be re-run. The receipts are the only record that the run failed, and nothing in the study's own return path reads them.

**Concrete trigger, constructed, not inferred.** Inputs: any `--provider live` run of `inv01_study` past the route check, with a `SETTLEMENT_EXPECTED_ROUTE` naming a model the gateway does not serve, or a free model whose `GET /models` does not list the pinned `resolved_model`. Wrong outcome: the adapter passes `_pre_dispatch_route_error` (the contract is well-formed and the endpoint matches), then `_response_meta` at `gateway_http.py:683-701` sees a returned model that differs from `expected.resolved_model`, stamps `route_error = RESPONSE_METADATA`, and `infer` at `:899-912` converts it to a `GatewayError` with `response_received=True`. Link 2 then writes `outcome: "failure"`, `response_class: "observed-provider-failure"`, `actual_cost = _billed_cost(error.usage)`. Link 3 absorbs. Exit 0, `freeze.json` and `study.json` written, zero effects. I did not dispatch this; the code path is a straight read of `gateway_http.py:899-912` into `broker.py:580-583` into `trajectory.py:548`.

**The fix that is missing is one assertion.** Somewhere between the campaign returning and the study writing its manifest, the run needs to ask whether any operation in the study's allocation tree settled with a `response_class` of `pre-send-route-refusal` or a `gw:` receipt whose `outcome` is not `success`, and to exit non-zero if so. `experiments/ad01/s09_receipt_diagnosability.py` already models exactly this: `Channel.DISPATCH_ATTEMPTED` is the field that separates `PRE_DISPATCH_REFUSAL` from `DISPATCHED_RESPONSE_LOST` (`:74-120`), and the module's own `proposed_receipt_shape` (`:432-491`) says so in its `why`. The broker does not write that field, so today the two hypotheses are conflated at the point where the decision to exit is made.

---

## 3. Findings

Severity is about what a wrong conclusion in the evidence costs. CONFIRMED means I executed the trigger or read a path with no branch that avoids it. SUSPECTED means I could not construct the trigger.

| # | Finding | File:line | Severity | Status |
| --- | --- | --- | --- | --- |
| F1 | Exit 0 after any absorbed refusal | `trajectory.py:548-554`, `agenda_policy.py:205-218`, `inv01_study.py:1144` | high | CONFIRMED |
| F2 | `s09_pilot` live path builds an adapter with no route | `s09_pilot.py:1091-1096` | high | CONFIRMED |
| F3 | `StudyGatewayGuard` passes refusals through unchecked | `s09_pilot.py:229-234` | high | CONFIRMED |
| F4 | `LiveGuard._route_failure` treats a missing route as no failure | `live_construct.py:289-291` | high | CONFIRMED |
| F5 | Preflight reads the future bundle to qualify launch | `s09_study_preflight.py:1233`, `:1111-1138` | high | CONFIRMED |
| F6 | Preflight passes a bundle in which nothing executed | `s09_study_preflight.py:1119-1127` | high | CONFIRMED |
| F7 | Retained policies run in-process on the use path | `s09_pilot.py:392`, `policy_step.py:190`, `trajectory.py:1406` | high | CONFIRMED |
| F8 | Use-phase policy admission is never recorded on the record it governs | `trajectory.py:1523-1539` | high | CONFIRMED |
| F9 | Use-record policy digest falls back to the bound digest | `s09_pilot.py:674`, `:682` | high | CONFIRMED |
| F10 | `executed_policy_digest` is read from the store, not the bytes that ran | `s09_pilot.py:570-576` | medium | CONFIRMED |
| F11 | Construction `_call` returns a settled receipt before dispatching | `construct.py:88-91` | high | CONFIRMED |
| F12 | A doubles run can seed a live run's receipts | `s09_doubles_forensics.py:229-264` | high | CONFIRMED (mechanism), antecedent INFERRED |
| F13 | Route reconciliation cannot see that a response was simulated | `gateway_http.py:683-701` | medium | CONFIRMED |
| F14 | A null provider charge is a VERIFIED zero | `s09_route_cost.py:96-105` | medium | CONFIRMED |
| F15 | The live/doubled boundary is `is_test_double` metadata plus a convention | `s09_arm_parity.py:104`, `:686-693` | high | CONFIRMED |
| F16 | AST and graph representations are hardcoded to the Boolean world | `boolean_ast_policy.py:572-593`, `boolean_graph_policy.py:264-265` | high | CONFIRMED |
| F17 | Sealed-observation detection keys on labels, not on membership | `packet.py:55-70` | medium | CONFIRMED |
| F18 | Every representation is checked against one per-world hardcoded schema | `s09_arm_parity.py:452` | high | CONFIRMED |
| F19 | Pilot raises on verification failure only when the report is complete | `s09_pilot.py:1370-1372` | medium | CONFIRMED |
| F20 | The use-phase policy is not asked which world it is in | `s09_pilot.py:357-377` | low | CONFIRMED |

### 3.1 F1. Exit 0 after any absorbed refusal. CONFIRMED, high

Covered in section 2. The trigger is any gateway refusal, and there are more of them than the route check: `gateway_http.py:711-733` refuses an incomplete contract, a paid route in free mode, a non-frozen endpoint and a non-frozen requested model. Each produces the same absorbed refusal and the same exit 0.

### 3.2 F7. Retained policies run in-process on the use path. CONFIRMED, high

The assignment asks whether anything in the apparatus re-executes a retained policy in a fresh process. The answer for the use path is no.

`scripts/s09_pilot.py:380-392`, `_use_phase_policy`:

```python
return policy_step.compile_step(source, origin="<use-policy:%s>" % arm)
```

`experiments/ad01/policy_step.py:181-192`, `compile_step`:

```python
namespace: dict = {}
exec(compile(source, origin, "exec"), namespace)
step = namespace.get(STEP_ENTRY)
return step if callable(step) else None
```

I checked what `run_use` and `_use_policy_action` contain. None of `run_step_out_of_process`, `run_policy_step`, `subprocess`, `LocalLauncher`, `exec_profile` or `scrub_env` appears in either. The object handed to `run_use` is a plain function. Measured: `type of the object run_use receives: function`.

So a model-acquired policy runs inside the study process, in the parent's interpreter, with the parent's memory, the parent's environment and no CPU, wall or output limit. The M2 assignment says "Use the existing bounded execution boundary." The investigation path honours it: `policy_step.run_policy_step` (`:424-445`) delegates to `method_exec.run_step_out_of_process`, which stages the source, verifies its digest, and dispatches through `LocalLauncher` with `scrub_env` (`src/settlement/exec_profile.py:104-113`) and `resource.setrlimit`. The use path bypasses all of it.

`policy_step.compile_step`'s own docstring says the gate exists precisely so that handing a source string is not mistaken for a governing policy. It is enforced in `run_policy_step` and not in `compile_step`. The use path calls the unguarded one.

Severity: a retained policy is model-authored source. A policy that loops burns the study's wall clock with no timeout; a policy that allocates burns the parent; a policy that reads the parent's globals reads the study's own in-memory state, including the `repertoire` and the `charter`. The verification rules in `method_exec.verify_step_source` (`:574-604`) are not applied on this path either, so a policy that would fail the STEP gate runs anyway.

I could not construct a *silent wrong-answer* scenario, because the policy does govern the method choice. I did construct the effect-reachability half, at `/tmp/r2_fresh2.py`: swapping the admitted `method_id` changes `selected` from `seed-sw-greedy` to `seed-sw-ddmin`. So the policy governs, in-process, unbounded, and its action is unrecorded (F8).

### 3.3 F8. The use-phase policy's admitted action is never recorded. CONFIRMED, high

`experiments/ad01/trajectory.py:1523-1539` writes the use record. Its complete key set, measured:

```
use record keys: ['arm', 'costs', 'domain', 'executed', 'executed_source',
 'fallback_reason', 'final_measure', 'freeze', 'freeze_digest',
 'initial_measure', 'normalized_reduction', 'operation_ids', 'output',
 'record_id', 'release_id', 'requested', 'selected', 'task_id', 'verdict', 'world']
  carries a receipt?  False | evidence? False
  carries the admitted action? False | policy_action? False
```

`operation_ids` is `[]` when `dsn is None`, and the record carries no receipt, no evidence and no action. The decision that chose the method is discarded the moment the method returns.

Then `scripts/s09_pilot.py:1285` fills the gap from the wrong place:

```python
saved.update(_use_policy_provenance(record))
```

`record` is the **investigation-phase** `_run_episode` record (`:1173-1183`), not anything the use phase produced. Its `policy_actions` (`:661-666`) are the boundary decisions from development, and its `executed_policy_digests` came from `_policy_digests(dsn, cid)` on the investigation campaign (`:668-674`).

Net effect: a use record's `policy_actions` names actions from a different campaign, and `ADMITTED_ACTION_FIELD = "policy_actions"` (`s09_study_preflight.py:45`) is exactly the field the preflight treats as proof that "the decision the policy admitted" is in the evidence. It is not. It is a different phase's decisions wearing the same key.

The `last_result` channel exists and is unused. `agenda_policy.py:596-605` writes the model's own text into `last_result` and passes it back to the next step. `trajectory._use_governed_member` (`:1399-1406`) passes `{}` for `last_result`, `[]` for `observations` and `open_questions`, so a use-phase policy is a one-shot function with no memory across the two use tasks. The two records are produced by two independent `decide` calls, each starting from empty state.

### 3.4 F9. `executed_policy_digest` falls back to the bound digest. CONFIRMED, high

`scripts/s09_pilot.py:671-682`:

```python
expected = bound_digest
if not expected and policy is not None:
    expected = policy["artifact"]["source_digest"]
executed = digests[0] if len(digests) == 1 else ""
...
"executed_policy_digest": executed or expected,
```

When a campaign ran two or more boundaries, `_policy_digests` returns two entries, `len(digests) == 1` is false, `executed` is the empty string, and the record's `executed_policy_digest` is the **bound** digest. The field's name says one thing and the code writes another. This is precisely the defect the handoff's reviewer correction warned about, restated in a different column: a policy digest is stamped onto a method-use record without being read off anything that ran.

`P0_POLICY_SOURCE` (`:294-305`) sets `{'used': True}` on its first return, so every P0 episode runs at least two boundaries in the common case. The fallback is the normal case, not the edge case.

### 3.5 F11 and F12. The construction receipt reuse is a real live-path hazard. CONFIRMED, high

`experiments/ad01/construct.py:88-91`:

```python
settled = _settled_text(dsn, operation_id)
if settled is not None:
    return {"operation_id": operation_id, "text": settled,
            "reused": True}
```

`_settled_text` (`:66-78`) looks up `receipts` by `operation_id` alone. `_op_id` (`:27-28`) is `ad01-%s-construct-l%d-%s` over `(cid, lineage, attempt)`, and `cid` is `campaign_id(world, arm, seq)`. None of those names the model, the gateway mode, the study root or the output directory.

`experiments/ad01/s09_doubles_forensics.py:229-264` documents the consequence and I confirm its reading of the code. `scripts/s09_pilot.py:782-810`, `_policy_requests`, re-reads `operations.payload` from the store and reports `request["model"]` from the stored row, not from the call argument. So a live run over a doubles-populated id reports `recorded-double` in a freeze that declares `mode: "live"`.

I mark F12's **mechanism** CONFIRMED and its **antecedent** INFERRED, matching the module's own label. I cannot confirm that a doubles run actually populated these ids on the dsn that produced the committed bundle, because the store that served the freeze is not in this cluster. `evidence_s09_m3_live/operations.json` holds 49 operations, all 13 model-inference receipts `success`. `evidence_s09_live_opus/operations.json` holds 36, with 8 success and 7 unknown. I did not attempt to settle it, and I am not the module.

What I add: the fix landed in `inv01_study` was to pin a route. **Pinning a route does nothing about this**, because the reuse happens before the adapter is consulted. `construct._call` reads the receipt and returns; `broker.dispatch_operation` is never called; no gateway is touched. A route guard at the study entry is structurally incapable of catching it.

### 3.6 F13. Route reconciliation cannot see a simulated response. CONFIRMED, medium

`src/settlement/gateway_http.py:683-701` reconciles only `model`, `provider`, `tier` and `endpoint`. `simulated` is not a route field. Measured, with a body carrying `simulated: True` and one without:

```
live   meta: {"adapter": "http", "contract": "c", "endpoint": "...", "model": "m",
  "provider": "openrouter", "request_endpoint": "...", "response_received": true,
  "returned_endpoint": null, "tier": "free"}
double meta: (identical)
identical: True
'simulated' survives into model_meta: False
```

`experiments/doubles.py`, `InvCQualificationDouble.infer`, sets `meta = {"simulated": True, "stream": name}` and then `meta["simulated"] = True` again, so it is always present on the double's own response. It reaches `receipts.content.model_meta` but nothing downstream reads it.

`tests/test_invr1_study_entry.py:118-124` had to add `"provider": "openrouter", "tier": "free", "endpoint": ...` to its HTTP double for the new route contract to be satisfiable. The comment on that test says the guard is working. It is working in the sense that a double must now *claim* to be on the route; nothing then checks whether it is. A double that claims the right provider and tier satisfies the same contract a live route does. `scripts/s09_verify.py:30-33` says so outright about the bundle:

> What the freeze asserts about the transport, checked for self consistency only: the bundle persists no per-request adapter or endpoint, so these cannot be compared against anything.

### 3.7 F15. The live/doubled boundary is metadata plus convention. CONFIRMED, high

`s09_doubles_forensics.py` is a forensic report about a *historical* bundle, not a boundary. It reads committed JSON and shells out to `psql`. It cannot fire during a run, so nothing it says constrains one.

What enforces the boundary today is `ArmRegistration.is_test_double` (`s09_arm_parity.py:104`), a caller-supplied boolean, and `compare_arms` (`:686-693`):

```python
has_real_arm = any(not arm.is_test_double for arm in arms)
if has_real_arm:
    status = "incomparable" if issues else "comparable"
else:
    status = "incomparable"
    issues.append(Incomparability(
        IncomparabilityReason.INSUFFICIENT_ARMS, arm_names,
        {"reason": "comparison has no real representation arm"}))
```

Two things follow. First, the flag defaults to `False` (`:203`), so a registration that forgets to set it is treated as real. The safe default is the unsafe one. Second, one `is_test_double=False` among several arms is enough to make the whole comparison "comparable", so a single mislabelled double in a three-arm set passes the gate.

The other half of the answer to the assignment's question: a double *can* reach a live lineage and a real evidence bundle today, and does. `construct._call` (F11) is reachable from a live run and is keyed on an id a doubles run populates. `experiments/doubles.py` is imported by `scripts/inv01_study.py:258` and `:268` and `:862`, and by `scripts/s09_pilot.py:893` inside `run_study`, which is a live path. `scripts/s09_pilot.py:1125-1129` also installs per-arm recording gateways for P1 and P2 *inside* a live run, when `gateway_mode == "doubles" and not provided_gateway`, which is the mode guard being the only thing between them.

### 3.8 F16 and F18. Every representation is hardcoded to one world, and the parity gate cannot see a second. CONFIRMED, high

`experiments/ad01/boolean_ast_policy.py:572-593` and `boolean_graph_policy.py:264-265` both build the view by delegating to `boolean_policy._shared_view`, and both hardcode the same requirement set:

```python
required = {"instrument", "task_id", "split", "max_queries", "remaining",
            "observed", "hypothesis_class", "action_schema"}
```

There is no world registry, no schema map and no parameter. Both representations raise on any world whose public state does not carry the Boolean-rule keys. `experiments/ad01/second_active.py` is a four-item ordering oracle, as CS-03 says, and neither representation can be pointed at it.

The consequence is that the parity harness cannot detect this. `s09_arm_parity.py:452` is the same `boolean_active` import chain. `compare_arms` checks representation-kind coverage and never asks which world a driver can express. A driver that only works on world A, compared against another on world A, is "comparable"; the identical driver on world B raises inside `decide` and becomes an `EPISODE_FAILED` **incomparability**, which reads as the policy's failure rather than the harness's. `boolean_policy._refusal` (`:152-165`) and `boolean_graph_policy._refusal` (`:296-309`) both swallow the exception and return a `stop` action carrying a `bridge_refusal` reason. So a representation that cannot express the world at all produces a clean `stop`, a zero reduction, and a comparison that reports a result.

### 3.9 F17. Sealed-observation detection keys on labels. CONFIRMED, medium

`experiments/ad01/packet.py:55-70` decides an observation is sealed from `access_label in {"hidden", "evaluator"}` or from the presence of one of seven `SEALED_KEYS`. Neither is membership in the protected set.

Measured. The use task `ad01-w1-within-sw-00` has raw keys `['family', 'fault', 'ops', 'seed', 'task_id', 'template', 'witness']`, and `public_task_view` correctly drops `fault` and `witness` because `PUBLIC_TASK_FIELDS` (`:47-52`) is an allowlist. An observation carrying a verdict but no label survives intact:

```
project_observations(no label): [{"capability_id": "c",
  "detail": {"reduction": 0.5, "witness": "obs-w-3"},
  "observation_id": "obs-y", "task_id": "ad01-w1-within-sw-00",
  "verdict": "preserved"}]
```

`witness: "obs-w-3"` reaches the policy view. The allowlist on the *task* is sound; the filter on the *observations* is a denylist of seven spellings. `trajectory.admit_investigation` (`:1884-1890`) does independently reject a `basis_reference` pointing at a non-dev task, so the reference channel is closed. The detail channel is not.

I could not construct a path that puts a non-dev observation in a dev policy's experience, because `_run_boundary` seeds only `obs-<task_id>-seed` and appends the campaign's own observations. So this is a hardening finding, not a live leak. Severity medium for that reason.

### 3.10 F14. A null provider charge becomes a VERIFIED zero. CONFIRMED, medium

`experiments/ad01/s09_route_cost.py:96-105`:

```python
charge = measured["provider_charge_units"]
return RouteCapacity(
    ...
    units_per_dispatch=Units(
        value=int(charge or 0),
        ...
        evidence=Evidence.VERIFIED),
```

The committed probe reports `charge_units: null`, `billed: null`, `charge_scale: null`. Measured:

```
units_per_dispatch: Units(value=0, ..., evidence=<Evidence.VERIFIED>)
  value: 0 | evidence: Evidence.VERIFIED
```

`int(None or 0)` is 0, and the evidence grade is VERIFIED, and the docstring at `:76-79` says "units_per_dispatch is zero because that is what the provider reported, and it is VERIFIED because it came from a committed settled receipt rather than from a default." Both halves are wrong: the provider reported nothing, and the grade certifies provenance of the *receipt*, not of the *value*. `measurement()`'s own `reads_as` string (`:75-76`) says "the provider charges nothing for this call", which is an inference from an absence.

This is CS-01. It is on my list because the assignment asks whether any `unknown` is scored as a real measurement, and this is the clearest instance in the tree. I did not chase the multiplication into `s09_exposure_ledger`; the denomination error starts here.

### 3.11 F19. Verification failure is conditional on completeness. CONFIRMED, medium

`scripts/s09_pilot.py:1370-1372`:

```python
if verdict["status"] != "pass" and report["complete"]:
    raise ValueError("pilot bundle fails verification: %s" % ...)
```

A bundle that fails `_verify.verify_bundle` and has an incomplete report is returned normally, from a live or controlled run, and `main` prints `s09-pilot <digest> episodes=N use=M model=K` and returns 0. An incomplete report is exactly what an arm-unavailable run produces, so the two conditions co-occur precisely when a run is degraded.

### 3.12 F20. The use-phase policy is not asked which world it is in. CONFIRMED, low

`scripts/s09_pilot.py:357-377`, `_use_phase_from`, hardcodes `.replace("__FAMILY__", "software")`. The family is the only token it varies; the method it names comes from the first repertoire member, and the policy body never reads `task['family']`. A graph-domain use therefore runs a software-named policy, which works only because `trajectory._use_governed_member` (`:1413-1417`) checks the member's scope and would refuse it. The refusal is correct; the policy is not wrong in a way the evidence would show.

---

## 4. Per-representation policy-view field lists

Measured, at the tip, from the actual builders rather than from their docstrings.

### 4.1 The Boolean world

`experiments/ad01/boolean_active.py:44-54`, `public_state(session)`, the world hands the harness eight keys:

| key | value | sealed? |
| --- | --- | --- |
| `instrument` | `"boolean-rule-v1"` | no |
| `task_id` | `"rule-dev-0011"` | no |
| `split` | `"dev"` | no |
| `max_queries` | 8 | no |
| `remaining` | budget | no |
| `observed` | list of `{x, y[4]}` for queried inputs only | no |
| `hypothesis_class` | `{form, n_inputs, n_outputs, class_digest, class_size}` | no |
| `action_schema` | `{version, format, actions, budget}` | no |

The hidden target tables never enter. `boolean_rule.make_task` (`:124-133`) returns `{task_id, split, seed, tables, instrument}` and `tables` is the answer. Measured: `leaks tables? False`.

### 4.2 The shared contract view, identical for all three representations

`experiments/ad01/boolean_policy.py:32-58`, `_shared_view`. Six top-level keys:

```
action_schema
instrument
observed
public_world
remaining
task_id
```

with

```
public_world        -> hypothesis_class, max_queries, split
action_schema       -> actions, budget, format, version
action_schema.actions -> construct, probe, stop
```

`observed` is a deep copy of the world's `observed`. `remaining` is a non-negative int, re-validated. `instrument` and `task_id` are strings. Nothing else crosses.

All three representations receive **byte-identical** views. `boolean_graph_policy.make_view` (`:264-265`) delegates to the same function, and `boolean_ast_policy._shared_view` (`:568-593`) is a line-for-line duplicate of it. Measured: `keys: ['action_schema', 'instrument', 'observed', 'public_world', 'remaining', 'task_id'] | identical to _shared_view: True`.

The duplicate is a finding of its own. Two copies of the projection, no shared owner, and the graph representation's field-accessor `_field_value` (`boolean_graph_policy.py:268-279`) reads the view by string path against a hardcoded `FIELD_TYPES` table (`:22-32`) that has drifted from the view: the table declares `public_world.split`, `public_world.max_queries`, `public_world.hypothesis_class.class_size`, `observed.count` and `observed.<0-3>.y.<0-3>`, but the view carries `hypothesis_class` with keys `form`, `n_inputs`, `n_outputs`, `class_digest`, `class_size`, so `public_world.hypothesis_class.class_size` resolves and `instrument` and `task_id` are both declared as guards but never usable as a guard value for anything other than an equality test against a literal.

**STEP representation.** `boolean_policy._run_shared_policy_step` (`:61-118`) stages `policy.py` and `step.json` in a temp directory, verifies the source digest twice (`:87-90` and `:108-110`), and dispatches through `LocalLauncher` with a scrubbed env. The child is `method_exec._STEP_DRIVER`, which `exec_module`s the policy and calls `STEP(view, state)`. Bounded: `policy_step.STEP_TIMEOUT_MS = 10_000`, `STEP_CPU_SECONDS = 10`, `STEP_MAX_OUTPUT_BYTES = 65_536`, `STATE_LIMIT_BYTES = 4_096`.

**AST representation.** `boolean_ast_policy._run_step` (`:506-555`) spawns `sys.executable -m experiments.ad01.boolean_ast_policy child request.json` with `env={"PATH": "/usr/bin:/bin", "PYTHONHASHSEED": "0", "PYTHONPATH": root}`, `start_new_session=True`, a wall timeout with `SIGKILL` on the process group, and an output byte cap. Inside, `_child_main` (`:482-503`) sets `RLIMIT_CPU` and `RLIMIT_AS`. The AST can only read the six view fields plus state: `_VIEW_TYPES` (`:47-54`) and `_stmt`'s field check (`:226-227`) refuse any `view.<name>` outside that set. Bounded the same way plus memory.

**Graph representation.** `boolean_graph_policy.choose_action` (`:312-336`) runs **in-process**. It is pure Python over a pre-parsed `GraphPolicy` of at most 64 nodes and 16 arms each, so the cost is bounded by the format rather than by a sandbox, and the state is `{at, progress}` validated against `STATE_LIMIT_BYTES`. No child process, no env scrub, no rlimit. It reads the view only through `_field_value`, which is restricted to `FIELD_TYPES` and the `observed` regex.

So the three representations have **three different execution boundaries** against **one view**. That is a comparability problem the parity harness does not check: `StepBudget` (`s09_arm_parity.py:83-95`) is passed identically to all three `choose_action` factories, but only STEP and AST honour it.

### 4.3 The AD01 STEP world

`experiments/ad01/policy_step.py:19-27` requires seven keys, and `materialize_view` (`:223-242`) builds exactly those:

| key | source | sealed? |
| --- | --- | --- |
| `task_content` | `packet.strip_task(task)` | no, allowlisted |
| `observations` | `packet.project_observations(...)` | denylist-filtered, see F17 |
| `open_questions` | caller-supplied list of strings | no |
| `last_result` | caller-supplied, the previous step's own model text | no |
| `eligible_methods` | capability ids only | no |
| `remaining` | `{queries, boundaries, dev_episodes, model_calls, policy_steps, model_calls}` | no |
| `contract_versions` | `{policy_step, child, packet}` | no |

`task_content` for `ad01-w0-dev-sw-00` measured `['family', 'ops', 'seed', 'task_id', 'template']`. For the protected use task `ad01-w1-within-sw-00` the raw keys are `['family', 'fault', 'ops', 'seed', 'task_id', 'template', 'witness']` and the public view drops `fault` and `witness`. That is the correct behaviour and the reason the AD01 world is not contaminated.

The divergence is that the AD01 world has **no shared-contract equivalent of the Boolean world**. `policy_action.view_contract()` (`:93-100`) declares six fields:

```
instrument, task_id, observed, remaining, public_world, action_schema
```

and the AD01 STEP view has seven different names. `s09_arm_parity` normalizes with `contract_view(public_state, arm_name=...)`, so the shared contract is a Boolean-world projection. The two worlds are compared through two unrelated view types, and `experiments/ad01/s09_arm_parity.py:17` imports `boolean_active` directly, so the harness itself is Boolean-only.

### 4.4 What I could not pin

`experiments/ad01/second_active.py`, the ordering world. I did not read it in full, so I am not reporting a field list for it. The M2 assignment names it as the second world and F16 establishes that no shipped representation can express it, which is the finding; the exact key set is the next reader's job.

---

## 5. Recommendations, in the order I would do them

1. **Refuse on a settled non-success gateway receipt.** One check, at the study boundary: if any `gw:` receipt under the study's allocation tree has `outcome != 'success'`, the study exits non-zero. This is the F1 fix and it is one query. `s09_receipt_diagnosability.py` already says which field would make it precise; until the broker writes `dispatch_attempted`, the outcome check is the strongest available.
2. **Pin the route in `s09_pilot`, or refuse the live mode.** F2 and F4. `_http_gateway`'s `route_mode="paid"` should go; a controlled run on a paid route is a decision someone has to make in writing, the way `_v1_route_from_env` makes it.
3. **Make the guard see the refusal.** F3. `StudyGatewayGuard.infer` and `LiveGuard._route_failure` both treat a `GatewayError` with `route_error` set and `response_received` False as a terminal condition, not a return value. That is the difference between the `inv01_study` fix, which moved the refusal to the entry, and a fix that survives any future source of refusal.
4. **Take the preflight's governance check out of the bundle.** F5 and F6. The apparatus is qualified by the deterministic per-representation checks the M2 assignment already specifies, run on their own namespace. The live artifact chain is joined after the effects. Delete `probe_policy_execution` rather than tightening it: digest diversity is the wrong predicate, and no tightening of "two distinct tuples" makes it causal.
5. **Run the use-phase policy through `run_step_out_of_process`.** F7. `s09_pilot._use_phase_policy` should hand back a source and `run_use` should execute it, so one policy cannot be bounded in development and unbounded in use.
6. **Record the admitted action on the record it governs.** F8. `trajectory._use_governed_member` already has the action in hand at `trajectory.py:1406`. Writing it onto the record is one line, and it makes `ADMITTED_ACTION_FIELD` mean what the preflight says it means.
7. **Make the operation identity carry the model.** F11 and F12. `_op_id` and `_policy_op_id` name the campaign, the lineage and the attempt. Adding the model or the freeze digest would make a doubles receipt unreachable from a live run by construction rather than by discipline. This is a schema change to operation ids, so it is a decision, not a patch.
8. **Invert the `is_test_double` default and require every arm to declare.** F15. One bool, defaulted the wrong way, with an OR over the arm set.

---

## 6. What I checked and did not find

So a later reader does not repeat the work.

- **No `sk-` credential appears in this file.** I read no key value into any artifact. The only credential-shaped string I typed was `"k"` in a throwaway script under `/tmp`.
- **The AD01 policy view is not contaminated.** `PUBLIC_TASK_FIELDS` is a real allowlist and it drops `fault` and `witness`. `trajectory.admit_investigation:1884-1890` independently blocks a non-dev `basis_reference`. The reference channel is closed.
- **`run_use` with no policy does not fall back to a method.** `trajectory.py:1344-1346` raises `_UsePolicyRefused` and `:1430-1451` writes `status: "refused"`, `selected: "refused"`, `executed: "refused"`. Measured. This is the S09R-02 fallback, and it is fixed.
- **The use-phase policy does govern.** F8's counterpart. Swapping the admitted `method_id` changes `selected`. The defect is that the decision is unrecorded, not that it is ignored.
- **`s09_arm_parity.compare_arms` does not call `boolean_active.run_episode` unconditionally on the wrong world.** It calls it on the Boolean world (`:543`); F16 is that this is the only world it can call.
- **The `s09_doubles_forensics` antecedent stays INFERRED.** I did not attempt to settle whether a doubles run populated the bundle's ids. Its own label is correct.

## 7. Reproduction

Every runtime claim ran from `/home/ubuntu/AI/Agent-Society-v2/.worktrees/r2-execution` with `/home/ubuntu/AI/Agent-Society-v2/.venv/bin/python`. The scripts are `/tmp/r2_exit0.py`, `/tmp/r2_boundary.py`, `/tmp/r2_pilot_live.py`, `/tmp/r2_preflight.py`, `/tmp/r2_views.py`, `/tmp/r2_leak.py`, `/tmp/r2_reach.py`, `/tmp/r2_fresh.py`, `/tmp/r2_fresh2.py`, `/tmp/r2_sim2.py`, `/tmp/r2_routecost.py`, `/tmp/r2_scoring.py`, `/tmp/r2_final.py`. None of them writes to the repository. The existing disposable stores `inv_r1_entry`, `inv_r1_full` and `inv_r1_probe` were read only; `inv_r1_full` and `inv_r1_probe` hold zero receipts.
