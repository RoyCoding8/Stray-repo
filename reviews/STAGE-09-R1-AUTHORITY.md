# Stage 9, R1: authority, budget, and crash recovery

Read-only review of `dd504e1` in `wt/r1-authority`. Nothing was modified. All database
work was read-only against the existing `invl02_live`; no database was created or
dropped, no live model call was made, the router was not touched.

`CONFIRMED` means I traced the code and constructed the input that triggers the wrong
outcome. `SUSPECTED` means the code looks wrong and I could not construct a reachable
trigger. Nothing below is included on a search result alone.

## The 8 required checks

| # | Check | Verdict |
|---|---|---|
| 1 | null-versus-zero billing | **FAILS outside `store`.** `store.receipt_actual_cost` is correct. `loop.read_measured_costs`, `records.py`, and `s09_route_cost` all fold null to zero. See F1, F2. |
| 2 | request-dependent reservation estimates | **HOLDS.** `broker._model_exposure` is a pure function of the validated request. Measured: 65 / 1101 / 9001 units for three different requests. |
| 3 | dimensional separation | **FAILS.** Reservation units are still subtracted from a dispatch count. See F3, F4. |
| 4 | durable resume consumes the remaining count only | **PARTIALLY HOLDS, with one rollover bug.** `resume_or_step` does not re-consume, but it never consumes a count at all. `agenda_policy` has an off-by-one reset. See F5. |
| 5 | old uncertain holds survive | **HOLDS for 3 of 4 release paths; one path drops them silently.** See F6. |
| 6 | finite new allowance can launch without settling the holds | **NOT TRUE in code, only in prose.** The 5563 units sit in two different study roots, and a new root's child capacity is computed from the *new* parent's `authorized`, which the holds never touch. See F7. |
| 7 | launches cannot exceed the allowance | **FAILS.** Ceilings are enforced on exactly one admission path, and the live path is not it. See F8. |
| 8 | unsuccessful response is an attributable attempted effect | **HOLDS.** A transport loss stays `unknown`, carries `response_received: False`, and drives the reservation to `uncertain`. Verified against the live r4 row. |

## Findings

| # | Severity | Location | Claim | Status |
|---|---|---|---|---|
| F1 | Critical | `src/settlement/loop.py:199` | `read_measured_costs` reports `"measured": charge or 0`, folding unknown billing into a measured zero | CONFIRMED |
| F2 | High | `experiments/ad01/s09_route_cost.py:100` | `int(charge or 0)` promotes a null `charge_units` to a VERIFIED zero cost per dispatch | CONFIRMED |
| F3 | High | `experiments/ad01/s09_study_preflight.py:489` | `Budget.remaining` subtracts reservation units from a dispatch ceiling and the evidence string calls the result "dispatches" | CONFIRMED |
| F4 | High | `experiments/ad01/s09_study_preflight.py:1405` | The dispatch allowance is read from an env var, so resume cannot roll it back | CONFIRMED |
| F5 | Medium | `experiments/ad01/agenda_policy.py:535` | Resume recomputes `model_remaining` as `6 - durable_now`, so durable spend already over 6 rewinds the cap to 0 and steps 7..N each get a fresh 6 | CONFIRMED |
| F6 | High | `src/settlement/team.py:1018` | `release_reservation` with no proof releases a `prepared` operation's reservation on a bare `reserved` state, with no never-sent evidence | CONFIRMED |
| F7 | Medium | `src/settlement/store.py:1289` | A new study root cannot reserve the 5563 held units, so the handoff's "provision the parent for held plus new" is not expressible | CONFIRMED |
| F8 | Critical | `src/settlement/store.py:1223` | Study ceilings are checked only inside `admit_study_operation`; every live dispatch path uses `ensure_operation`, which never reads `study_authority.ceilings` | CONFIRMED |
| F9 | High | `src/settlement/authority.py:365` | `verify_ledger` reports `match: true` for a study whose exposure was settled to zero, and `match` is independent of `unknown` and `unknown_usage` | CONFIRMED |
| F10 | Medium | `experiments/ad01/records.py:578` | `if usage.get("billed"):` silently drops a null `billed` from `measured_charge` with no entry in `costs_unknown` | CONFIRMED |
| F11 | Medium | `src/settlement/store.py:1282` | A declared-but-uncounted ceiling name is silently unenforced rather than refused at authorization | CONFIRMED |
| F12 | Low | `experiments/ad01/policy_step.py:340` | `durable_model_calls` counts one unrelated operation as a policy model call | CONFIRMED |
| F13 | Low | `experiments/ad01/s09_study_preflight.py:100` | The 25-unit figure in `s09_route_cost` is a live re-derivation, not a constant, and the module's "fixed estimate" prose is wrong | CONFIRMED |
| F14 | Low | `src/settlement/store.py:1287` | A ceiling refusal raises `InsufficientResources` inside `transact`, which journals the refusal under the caller's `request_id`, so a later legitimate admission with the same id is refused as a replay | CONFIRMED |

## Detail

### F1. `read_measured_costs` folds unknown billing into a measured zero (Critical, CONFIRMED)

`src/settlement/loop.py:197-204`:

```python
return {"operation_id": operation_id,
        "dispatch_state": (row or {}).get("dispatch_state", "missing"),
        "measured": charge or 0,
        "provider_charge_units": charge,
        "billed": billing,
```

`charge` is `None` whenever `_billing_from_usage` returns `(None, None)`, which is
exactly the case the free route produces: `billed` is null. The sibling fields
`provider_charge_units` and `billed` correctly carry `None`. `measured` then carries
`0`.

The consumer is `loop.run_boundary:559`, which puts that value into the durable
transition journal:

```python
costs_measured={"measured": costs["measured"],
                "provider_charge_units": costs["provider_charge_units"],
```

Failure scenario. One `model-inference` operation on the confirmed free route returns a
settled success receipt with `usage.billed = null`, `usage.charge_units = null`. That is
byte for byte the shape of the committed probe at `evidence_s09_route_probe/probe.json`.
`read_measured_costs` returns `{"measured": 0, "provider_charge_units": None,
"billed": None, "unknown": ["gw:..."]}`.

The `unknown` list is populated correctly, so the information is not lost. But
`measured: 0` and `provider_charge_units: None` sit side by side, and the field named
`measured` is the one a reader sums. Any aggregate that sums `costs_measured.measured`
reports a real measurement of zero for a cost nobody measured. That is the same
null-to-zero fold CS-01 names, one layer down from where the handoff found it, and it is
in the durable journal rather than in a preflight that only runs once.

I checked for a folding-to-zero consumer before reporting this. `verify_ledger` uses
`store.receipt_actual_cost`, not this function, so it is not affected. `records.py` has
its own copy (F10) with the same defect.

### F2. `route_capacity` promotes a null charge to VERIFIED zero (High, CONFIRMED)

`experiments/ad01/s09_route_cost.py:95-104`:

```python
charge = measured["provider_charge_units"]
return RouteCapacity(
    ...
    units_per_dispatch=Units(
        value=int(charge or 0),
        ...
        evidence=Evidence.VERIFIED),
```

`measurement()` reports the free route's `charge_units` as `None` and then describes it
at line 74 as `"the provider charges nothing for this call"`. `int(charge or 0)` turns
that unknown into a verified zero.

This is the defect CS-01 already names, and I confirm it rather than re-deriving it: the
`Units` value is `0` with `Evidence.VERIFIED`, which is exactly what
`budget_for_new_study` requires before it will produce a `Budget` at all
(`s09_exposure_ledger.py:586-594`). The `VERIFIED` marker is what makes a ceiling
derivable from an unmeasured quantity.

The consequence for the new study is currently masked. Because the value is zero,
`route_capacity_from_freeze` computes `max_dispatches * 0 = 0` at
`s09_exposure_ledger.py:278`, and `budget_for_new_study` then refuses:

```
carried exposure of 5563 units is not below the authorized ceiling of 0
```

So the wrong zero currently produces a refusal, not a launch. The defect becomes a launch
the moment anyone provisions a nonzero ceiling, which is what the handoff instructs in
M1. The fix has to land before the ceiling does.

### F3. `Budget.remaining` subtracts units from a dispatch count (High, CONFIRMED)

`experiments/ad01/s09_study_preflight.py:486-492`:

```python
@dataclass(frozen=True)
class Budget:
    already_spent: int
    ceiling: int
    exposure: int

    @property
    def remaining(self) -> int:
        return self.ceiling - self.already_spent - self.exposure
```

and the passing evidence at lines 1414-1419:

```python
return Outcome(name, Pass(Evidence(
    "ceiling %d less carried exposure %d (%s) less already-spent %d "
    "leaves %d dispatches for study %s" % (
        budget.ceiling, budget.exposure, seen.exposure.source,
        budget.already_spent, budget.remaining, seen.exposure.study_id),
```

`exposure` is `ExposureLedger.carried_units`, the 5563 broker reservation estimate.
`ceiling` is `study_ceiling()`, a unit count. `already_spent` is a dispatch count from
`S09_STUDY_CALLS_ALREADY_SPENT`. The three terms are three different dimensions and the
result is labelled "dispatches".

The module's own `ExposureLedger` docstring at line 448 says the opposite:

> Units, not operations. The last two settlements are worth 5563 units between them and
> settled a handful of operations, so any budget computed in operations would clear by
> six orders of magnitude.

The dataclass below it then computes a budget in operations.

### F4. The dispatch allowance is an env var, so resume cannot roll it back (High, CONFIRMED)

`s09_study_preflight.py:1184-1186`:

```python
def reported_spend() -> int | None:
    raw = config_values().get(REPORTED_SPENT_VAR, "")
    return int(raw) if raw.lstrip("-").isdigit() else None
```

`REPORTED_SPENT_VAR` is `S09_STUDY_CALLS_ALREADY_SPENT`. Nothing reads the durable
operation table.

Failure scenario. The handoff requires "durable resume consumes the remaining count only"
and lists "resumed-count rollback" as a required rejecting example in M4. Launch a study
that dispatches 10 sends, crash, resume with the same env var still reading `0`. The
preflight reports 10 sends remaining. The 10 already-spent sends are re-spendable. Any
run that sets the variable from a bundle rather than from `SELECT COUNT(*) FROM
operations` gets this, and `scripts/invl02_live.py:1299 _output_already_spent` shows the
correct durable derivation already exists in the codebase for one study family, which
makes the env var the outlier rather than a pattern.

By contrast `scripts/s09_pilot.py` and `experiments/ad01/live_construct.py` do enforce a
durable ceiling, through `LiveGuard.dispatch_count` initialised from a durable count at
`scripts/invl02_live.py:1299`. The preflight is the layer that is behind.

### F5. Durable resume recomputes the model cap from a rewound base (Medium, CONFIRMED)

`experiments/ad01/agenda_policy.py:532-541`:

```python
packet_allowance = int(
    (dict((seen or {}).get("remaining") or {}).get("model_calls", 6)))
entry_model = policy_step.durable_model_calls(
    self._dsn, self._cid, self._seq)
for index in range(start_index, self._max_policy_steps):
    durable_now = policy_step.durable_model_calls(
        self._dsn, self._cid, self._seq)
    spent = durable_now - entry_model
    model_remaining = min(packet_allowance - spent, 6 - durable_now)
```

The first term correctly counts only what this run spent: `packet_allowance - (durable_now
- entry_model)`. The second term does not. `6 - durable_now` is an absolute cap read
against the cumulative durable total, so once `durable_now >= 6` the second term goes
negative, `min` selects it, and `model_remaining` is clamped to `max(int(...), 0)` = 0.
That part is safe.

The rollover is on the other side. If a prior run already made 6 durable calls, then
`durable_now = 6` gives `6 - 6 = 0` and the step is refused, which is right. But
`entry_model` is re-read fresh on every resume, so a resume that starts when
`durable_now = 6` has `entry_model = 6`, `spent = 0`, and `packet_allowance - spent =
packet_allowance`. The absolute term still pins it to 0. So the two terms disagree
whenever `packet_allowance > 6`, which is the normal case: the packet carries the
campaign-level `remaining.model_calls`, defaulting to 6 but settable higher.

Failure scenario. `packet_allowance = 20`, `durable_now = 7`, `entry_model = 6`,
`spent = 1`. Term one gives `20 - 1 = 19`. Term two gives `6 - 7 = -1`. `min` selects
`-1`, clamped to 0, and the step is refused even though 19 remain. The cap is enforced
against the absolute floor, not against what remains, so it under-spends rather than
over-spends. The safe direction, but it makes the two-term expression wrong and it means
a campaign can never use a packet allowance above 6.

`s09_durable_state.resume_or_step` is not implicated. It holds no count: it loads a
committed step and returns it, and its caller supplies the count. That is the shape the
handoff asks for, and it is correct. The defect is in the caller.

### F6. `release_reservation` drops a reservation with no never-sent evidence (High, CONFIRMED)

`src/settlement/team.py:1016-1026`:

```python
state = op["dispatch_state"]
if state == "prepared":
    if op["reservation_id"] is not None:
        freed = store.release_reservation(
            dsn, Command(
                request_id=f"{cmd.request_id}:release:{operation_id}",
                payload={"reservation_id": op["reservation_id"]}))
```

`release_reservation` at `store.py:676`:

```python
proof = None
if res["state"] == "uncertain" or "never_sent_proof" in cmd.payload:
    ...
    proof = _never_sent_proof(cmd.payload, str(res["id"]), generation)
```

For a `prepared` operation the reservation is still in state `reserved`, never
dispatched, and the payload carries no proof. Both conditions are false, so `proof`
stays `None` and lines 694-698 run unconditionally:

```python
cur.execute(
    "UPDATE allocations SET reserved = reserved - %s WHERE id = %s",
    (int(res["amount"]), res["allocation_id"]))
cur.execute("UPDATE reservations SET state = 'released' WHERE id = %s", (res["id"],))
```

A `prepared` operation genuinely was never sent, so the release is factually right. The
defect is that it happens with no evidence recorded at all: the `resources.released` event
carries `{"reservation_id": ..., "never_sent_proof": None}`, and `verify_ledger` cannot
distinguish this from a release backed by a launcher proof. Every other release path in
`store.py` (`confirm_cancellation:1640`, `reconcile_operation:1851`) demands
`_never_sent_proof` and refuses without it. This one does not.

For the 5563 units specifically this is not currently reachable, which I checked: the
ad01 hold is `unresolved/unresolved`, not `prepared`, and `team.py` routes `unresolved`
to `request_cancel` rather than to release. So this is a latent gap in the invariant, not
a live loss. Severity is High because it is the one release path with no evidence, and the
next writer who adds a `prepared` state to that branch inherits it.

### F7. A new study root cannot provision for the held units (Medium, CONFIRMED)

`src/settlement/store.py:1289-1298`:

```python
cur.execute("SELECT * FROM allocations WHERE id = %s FOR UPDATE", (child_id,))
child = cur.fetchone()
if child is None:
    parent = _require_child_capacity(cur, parent_id, exposure)
```

`_require_child_capacity` computes `parent.authorized - parent.consumed - parent.reserved
- SUM(children.authorized)`. For a fresh study root those are all zero, so any positive
exposure is admissible regardless of the 5563.

The handoff says (M1 item 2): "If a shared parent ceiling is required, explicitly
provision enough for the held amount plus the new finite allowance under the user's
standing authorization; do not release the old holds to make room."

There is no such shared parent. I read the two holds out of `invl02_live`:

| Reservation | Units | Allocation | Parent |
|---|---:|---|---|
| `res-ad01-ad01-w0-I-72-b0-ad01-w0-dev-sw-00-construct-l1-init` | 3269 | `ad01-ad01-w0-I-72-b0-ad01-w0-dev-sw-00-construct` | `ad01-campaign-ad01-w0-I-72` |
| `res-invl02-output-872608eb94c3-P1-audit-0023-a1` | 2294 | `ad01-campaign-invl02-output-shape-550b-r4` | `NULL` |

The r4 allocation is a root with no parent. The ad01 hold sits under a different
campaign. A new study root is a third tree. The 5563 units are therefore not a barrier
to a new finite allowance, and equally are not carried by it. Check 6's answer is that
the two conditions are disconnected: nothing enforces "the new allowance covers the old
holds", and nothing prevents the old holds from being silently excluded from the new
root's accounting. The handoff's own framing (a parent ceiling to provision) does not
match the shape the data has.

### F8. Study ceilings are enforced on one path, and it is not the live one (Critical, CONFIRMED)

`grep -n "ceilings" src/settlement/store.py` returns exactly four lines: 1273, 1274, and
the `_ceiling_value` helper. The entire enforcement is inside `admit_study_operation`
at line 1223, and `admit_study_operation` is called from exactly one non-test place:
`authority.admit_study_call` at `authority.py:230`. `admit_study_call` is called from
tests only.

Every live dispatch path goes through `broker.ensure_operation` (line 246), which calls
`store.prepare_operation` (line 1160), which calls `_prepare_operation` (line 1120).
Neither reads `study_authority.ceilings`. The only things `_prepare_operation` consults
are the allocation's free units and, when an attempt is bound, its lifecycle.

The three live call sites:

- `experiments/ad01/learner.py:231` — `broker.ensure_operation(..., effect=MODEL_INFERENCE, ...)`
- `experiments/ad01/agenda_policy.py:438` — same, for the policy reasoning call
- `experiments/ad01/method_exec.py:743` — same, for `SANDBOX_EXEC`

And the freeze that declares the ceilings is real: `scripts/s09_pilot.py:66` authorizes
`s09-m5-root` with `ceilings={"model_calls": 100, "construction_calls": 4}`.

Failure scenario. `s09_pilot` runs against a study root whose ceiling is
`model_calls: 100`. A learner loop runs 100 model calls. The 101st goes through
`ensure_operation`, which checks only that the allocation has free units. `ad01-campaign-
s09-m5-root` is authorized for 2,000,000 units, so a 2048-token call at roughly 3000
units is admitted. `verify_ledger` on that root returns `match: true`. The freeze's
`max_model_calls` is never consulted by any code path that a live send takes.

The `LiveGuard` in `scripts/s09_pilot.py:1110` and `live_construct.py:212` does enforce
a dispatch ceiling, but in the process, from `already_spent`, which for the pilot's
frontier arm is the same env var as F4. Two independent ceilings, neither of them the one
the freeze declared.

This is the one that decides whether check 7 has a real answer. It does not.

I checked the obvious counterargument: is `_admission_checks` a second enforcement point?
It is, for the dispatch half, but it checks pause, grant version, attempt ownership and
release, never a count (`store.py:747-772`).

### F9. `verify_ledger` calls a settled-to-zero exposure a match (High, CONFIRMED)

`src/settlement/authority.py:379-381`:

```python
"unreceipted": sorted(row["id"] for row in unreceipted),
"match": not conflicts and consumed == summary["expected_consumed"]
and reserved == pending,
```

`pending` and `unknown` are computed and returned but `match` does not read either. The
r4 and ad01 rows in `invl02_live` return `match: true` today, correctly, because their
`pending` matches their `reserved`. The problem is that a study whose exposure is settled
away also returns `match: true`.

I confirmed the trigger by running `_summarize_receipts` on the real ad01 receipt row and
then on the same row with `reservation_state` moved to `settled`, which is exactly what
`_settle_amount(cur, reservation_id, "failure", actual=0)` writes (`store.py:428-439`):

```
today                : pending 3269
after settle(actual=0): pending 0, expected_consumed 0
verify_ledger.match would report: True
```

The 3269 units leave the ledger, `expected_consumed` is 0, `consumed` is 0, `reserved` is
0, `pending` is 0, and every term of the equality holds. `verify_ledger` says the
ledger reconciles. It does not report that the study owes 3269 units of exposure it no
longer holds, because the one function whose job is to say so (`_summarize_receipts`
line 313-316) only records an *unbilled* unknown in `unknown_usage`, and `match` ignores
`unknown_usage` too.

What `verify_ledger` does not check, in full:

- Whether any `unknown`-outcome receipt exists. `unknown` is returned, not consulted.
- Whether any receipt has unmeasured usage. `unknown_usage` is returned, not consulted.
- Whether a reservation was released without a never-sent proof (F6).
- Whether `measured` and `expected_consumed` agree with each other.
- How many physical dispatches occurred. It reads no `_dispatch_generation`. This is the
  quantity the r4 bundle got wrong by one, and the authority function that a study would
  use to check itself cannot detect that class of error.

The last one is the sharpest. `verify_ledger` on `invl02-output-shape-550b-r4` returns
`match: true` and reports no dispatch count at all, so the r4 failure mode (a bundle
claiming zero dispatches where the store holds one) is outside its remit by
construction. The handoff's M4 requires an offline recomputation of accounting; this
function is the obvious candidate and it will not catch that.

### F10. `records.py` drops a null `billed` without recording it as unknown (Medium, CONFIRMED)

`experiments/ad01/records.py:577-584`:

```python
measured_charge = 0
for op_id in seq_ops:
    for receipt in receipts_by_op.get(op_id, []):
        ...
        if usage.get("billed"):
            try:
                measured_charge += int(
                    usage.get("charge_units", 0) or 0)
            except (TypeError, ValueError):
                unknown.append(str(
                    receipt["receipt_identity"]))
```

A receipt with `billed: null` is not billed, so the branch is skipped. It is not added
to `unknown` either. `measured_charge_units` exports 0 and `costs_unknown` does not
mention it.

The distinction that matters is the one the code already draws elsewhere in the same
loop: a receipt with `outcome == "unknown"` goes into `unknown`. A receipt with
`outcome == "success"` and `billed: null` is a *decided* receipt with unmeasured cost,
and this loop treats it identically to a receipt measured at zero. That is the exact
`null-versus-zero` error the handoff requires be checked, in the export path that M4
depends on for offline recomputation.

### F11. A declared-but-uncounted ceiling is silently unenforced (Medium, CONFIRMED)

`src/settlement/store.py:1274-1288`:

```python
for name, raw_limit in ceilings.items():
    limit = _ceiling_value(raw_limit)
    counter = _ceiling_counter(name)
    if limit is None or counter is None:
        raise SettlementError(f"unsupported study ceiling {name}")
```

and `is_ceiling_name` at line 124 accepts seven names that `_ceiling_counter` maps to
`None`: `boundaries`, `witness_queries`, `dev_episodes`, `lineages`, `deadline_s`,
`trajectories`, `diagnostic_queries`. Verified directly.

Those are in `DECLARED_CEILINGS` at line 118 with an explicit comment that the layer
records but does not count them. So the authorization path accepts a declaration that
the enforcement path cannot honour, and the refusal only surfaces on the first
admission, as `SettlementError` from inside `admit_study_operation`, whose code is
`INVALID_INPUT`. `admit_study_call` maps that to `Refusal(reason="admission-refused")`,
which is indistinguishable from a malformed action.

Failure scenario. A study freezes `{"dev_episodes": 4, "model_calls": 6}`. It
authorizes. It dispatches normally. `dev_episodes` is never checked by any code path,
so the cap of 4 does not exist. The sheet says it does. The handoff's M3 requires
freezing "meaningful per-arm compute/oracle limits", and oracle limits are precisely
the ones that land in this set.

Whether that is a defect or a deliberate scope statement depends on intent, and the
comment says it is deliberate. The defect is the *split*: `is_ceiling_name` and
`_ceiling_counter` disagree, and the disagreement surfaces 2000 lines away from where a
reader would look for it.

### F12. `durable_model_calls` counts an unrelated operation (Low, CONFIRMED)

`experiments/ad01/policy_step.py:339-348`:

```python
prefix = "ad01-%s-policy-s%d-model-" % (cid, seq)
like_construct = "%" + cid + "%-b" + str(seq) + "-%construct%"
like_any = "%construct%"
cur.execute(
    "SELECT count(*) AS n FROM operations"
    " WHERE payload->>'effect' = 'model-inference'"
    " AND (starts_with(id, %s)"
    " OR (id LIKE %s AND id LIKE %s))",
    (prefix, like_construct, like_any))
```

I ran this against `invl02_live` for `cid=ad01-w0-I-72, seq=0`. It returns 1, and the
row it counted is `ad01-ad01-w0-I-72-b0-ad01-w0-dev-sw-00-construct-l1-init`, an
`ad01-campaign` construction operation, not a `policy-s0-model-` operation.

So for this campaign the policy-step remaining count is permanently reduced by one, from
a construction call. Since F5 shows the count is used as an absolute floor, the effect is
conservative here. It is a real miscount and it feeds the resumed-count computation, so I
report it, at Low, because the demonstrated direction is under-spend.

### F13. The 25-unit figure is derived, not fixed (Low, CONFIRMED)

`s09_route_cost.py:40` names `RESERVATION_UNITS_PER_DISPATCH = 25` and line 114 says
"the store still requires a reservation of 25 units to admit a dispatch". The probe
request was `max_output_tokens: 16` on a 33-character prompt. I recomputed it:
`33 // 4 + 1 + 16 = 25`. It is not a constant, it is the broker's schedule for that
specific request, and the handoff's M1 phrase "a fixed 25-unit smoke-request estimate"
is describing the module's own mislabelling rather than the store's behaviour.

Worth correcting in the module's prose because the handoff cites it. Not a code defect.

### F14. A ceiling refusal is journaled under the caller's request id (Low, CONFIRMED)

`store.transact` catches `SettlementError`, rolls back, and re-journals the refusal at
lines 244-257 with `ON CONFLICT (request_id) DO NOTHING`, i.e. it *keeps* the refusal
row. `admit_study_call` builds `request_id=f"admit-study-{study_root}-{operation_id}"`,
which is a pure function of the study and the operation, with no attempt or generation
component (`authority.py:231`).

Failure scenario. Attempt 1 admits `op-1` with a reservation the store can cover. The
`model_calls` ceiling is reached, so the refusal is journaled under
`admit-study-root-op-1`. Attempt 2 for the same operation, now with a smaller request and
a different reservation amount, computes a different `payload_digest` but the same
`request_id`, and `transact` raises `ConflictPayload("request identity ... reused with
different payload")` at line 235 before the handler runs. `admit_study_call` maps that to
`Refusal(reason="admission-refused")`. The operation can never be admitted under that id
again.

Idempotent replay is the point of the journal, so a stable id is right for a retry of the
same intent and wrong for a different intent. `LiveGuard` avoids this with
`_OutputGuard.infer` restoring `dispatch_count` on replay (line 233), which is a
workaround at the wrong layer.

I could not construct a case where this loses exposure. It refuses an admission, which
is the safe direction. Low.

## What the required checks did not ask, and I checked anyway

**Two concurrent processes against one shared cluster.** Every write goes through
`store.transact`, which opens `SERIALIZABLE` and takes `SELECT * FROM control WHERE id = 1
FOR UPDATE` as its first statement (line 220). That single row is a global mutex, so
`admit_study_operation`, `_take_reservation`, `_settle_amount` and `_prepare_operation` are
all serialized. I could not construct a double-spend of the same allowance, and I am not
claiming one. The cost is that every settlement on the shared cluster serializes behind
one row, which is a throughput property, not a correctness one.

The one genuinely non-transactional write is `take_correction` at `authority.py:503`,
which uses `db.connect` directly rather than `transact`. It does take `SELECT ... FOR
UPDATE` on the `study_corrections` row, and it handles the absent-row case by inserting,
so two concurrent first-time callers can both compute `used = 0`. Whether they both
insert depends on whether the upsert serializes; I traced it and the `ON CONFLICT DO
UPDATE SET used = study_corrections.used + 1` makes the second caller's `used` field
`used + 1` where its own `used` was 0, which is correct, but the returned `allowed` is
computed from the pre-update local `used`, so the second caller can be told `allowed:
true` when the durable `used` is 2. `_spend_correction` at `loop.py:399` then increments
`state.corrections_used` from that answer. Two concurrent corrections against a budget of
1 can both be told they were allowed. SUSPECTED, and low impact: the next call reads the
durable `used` and refuses.

**Crash between operation creation and receipt write.** The reservation is taken and the
operation inserted in the same transaction as the admission, so the exposure is never
lost, only unattributed. After a crash the operation sits `prepared` or `dispatching`
with a `reserved` reservation. `restart_reconciliation` (`store.py:1949`) finds it,
`broker.sweep(repair=True)` drives it, and with no launcher outcome the path lands on
`reconcile_operation(resolution="unresolved")`, which leaves the reservation `reserved`
and the operation `unresolved`. The exposure is held, not lost. That is correct and I
found no path where it silently becomes zero.

The one gap is the `prepared` case, which is F6: it is the only path that releases
exposure with no evidence, and a crash between admission and dispatch is exactly how a
`prepared` operation with a live reservation comes to exist.

**Double settlement.** `_settle_amount` returns `(False, "already settled", 0)` on a
reservation already in state `settled`, and the only caller that treats that as an error
is `agenda01/runner.py:315`, which passes the result to an `_ok` helper. Idempotent.
`admit_receipt` also short-circuits on `bool(op["settled"])` at line 1566 before reaching
`_settle_amount`. No double-spend path found.

**Receipt attached to the wrong operation.** `_validate_receipt` (`store.py:1425-1428`)
compares `content["operation_id"]` against the operation, and
`_receipt_identity_problem` (`broker.py:325-339`) does the same at the broker boundary,
with a separate rule for `identity-failure` receipts. `receipts.receipt_identity` is the
primary key and `admit_receipt` checks a global uniqueness conflict at line 1491,
marking both operations `conflict`. I found no path that attaches a receipt to the wrong
operation.

## The single most serious thing

**F8. The freeze's dispatch ceiling is not enforced on any live path, and two other
ceilings (F3, F4) are arithmetic on units and on an env var rather than on the durable
operation table.**

Three separate places each hold part of the launch bound, none of them is the one the
freeze declared, and the one the freeze declared is read by code no live send reaches.
`s09_pilot.py:66` authorizes `model_calls: 100` and `construction_calls: 4` into
`study_authority.ceilings`; `store.admit_study_operation` is the only reader of that
column; `authority.admit_study_call` is that function's only non-test caller; and no
production code calls `admit_study_call`. Meanwhile the preflight that a study is gated
on computes its "remaining dispatches" by subtracting 5563 reservation units from a unit
ceiling, minus a number an operator typed into an environment variable.

The consequence is that the 64-send bound M3 freezes is not enforceable through the
authority the campaign built. A run that exceeds it will do so without any code objecting,
`verify_ledger` will return `match: true` (F9, and it never counts dispatches at all), and
the bundle will record whatever the in-process guard happened to count. That is the r4
failure mode, with the checking machinery pointed at the wrong layer.

Fix order, as I would sequence it: F8 and F3 first, because they are the difference
between a bound and a note. F4 next, since it is what makes a resume re-spendable. F9
last among these, because it is what let the first three go unnoticed. F2 must land before
any nonzero ceiling is provisioned, or the ceiling will be derived from a null.

## Severity rationale

Critical means the mechanism the campaign relies on to bound a live run does not hold.
F1 and F8 are that. High means a number a human will act on is wrong in a way that
survives into committed evidence. F2, F3, F4, F6, F9, and F10 are that. Medium means the
invariant is incomplete in a way I could not make fire against the current data. F5, F7,
F11 are that. Low means I found it and it does not currently change an outcome. F12, F13,
F14 are that.

I did not pad the list. Four further suspicions I could not construct a trigger for, and
which I therefore left out rather than dressing up: `evidence_epoch` staleness on
commands that omit the field (`_check_evidence` at `store.py:165` returns immediately when
`evidence_epoch` is absent), a second digest-coverage gap in `_check_operation_replay` for
`study_root` and `budget_kind` (both are digest-covered, but `retries` is not, and the
exposure formula multiplies by `retries + 1` so a changed retry count with an equal
exposure would pass replay), `note_phase` accepting an `operation_id` from any study as
long as it is a decided non-conflict operation, and `authorize_study` creating a
`store_identity` row before the study row when the study row insert then fails, leaving a
store with a fingerprint and no authority.
