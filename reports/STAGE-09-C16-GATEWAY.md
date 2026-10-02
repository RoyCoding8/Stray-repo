# C16: one comparison per route field

`POST /v1/chat/completions` returns `provider: "Nvidia"` for the frozen route
whose contract spells the same vendor `"nvidia"`. `GET /v1/models` carries no
`provider` field at all. The catalog half of the route check folded case and
accepted the value; the response half compared with `==` and refused the same
value as `response_metadata`, **after the tokens were spent**.

Two of the earlier claims about this were wrong, and are corrected here. There
was a `provider` field, and there was a casing defect. Both were missed by
reading the models listing instead of a completion response.

## The defect

One field, two predicates, in one file:

| half | site | predicate |
|---|---|---|
| catalog | `gateway_http.py:391` (`reconcile_model_route`) | `provider.lower() != expected["provider"].lower()` |
| response | `gateway_http.py:752` (`_response_meta`) | `route["provider"] != expected.get("provider")` |

The verification half and the enforcement half disagreed about the same field
on the same response. The asymmetry was the defect, not the `==`.

## What was measured, and what it decided

Both classification questions were settled by sending, not by reading.

**`provider` names the vendor, not the aggregator.** The same model was
dispatched under three ids in one minute:

| id | returned `provider` | catalog `owned_by` |
|---|---|---|
| `nvidia/nemotron-3-ultra-550b-a55b:free` | `Nvidia` | `Openrouter` |
| `openrouter/nvidia/nemotron-3-ultra-550b-a55b:free` | `Nvidia` | `Openrouter` |
| `kilo/nvidia/nemotron-3-ultra-550b-a55b:free` | `Nvidia` | `Kilo API` |

`provider` is invariant across the change of aggregator; `owned_by` is not.
They are different fields, so mapping `owned_by` onto `provider` — the
alternative a reader would reach for — would refuse every correct response.
`owned_by` is not a fallback for `provider`.

**A model id is a key, not a word.** The gateway answered
`NVIDIA/nemotron-3-ultra-550b-a55b:free` with HTTP 503 `auth_not_found` and
`nvidia/...` with HTTP 200 in the same minute. Ids are exact lookups into the
128-entry catalog, so folding one would admit a key the catalog cannot answer
for. Only labels fold.

## What `provider` is

**A routing field.** The gateway is contractually obliged to return it, and an
unexpected value is a refusal, not a note. Three reasons, in order of weight:

1. The whole point of the contract is that a study can say which vendor
   answered. A field that can be absent, or that can disagree without
   consequence, attests nothing.
2. The study records `provider` beside the result
   (`experiments/ad01/live_construct.py:342`), and analysis reads it back. A
   note that is allowed to drift is a field that will.
3. The catalog already refuses an entry that contradicts the frozen namespace
   (`:391`). If the catalog may refuse, the response may too; the two halves
   are one check, and a check that fires on one surface only is not a check.

So an absent `provider` is refused rather than inferred. That was already the
behaviour — `None != "nvidia"` refused by accident — and it is now a decision a
reader can find instead of a coincidence. The verdict is recorded in the
comment at `_response_meta` and in the table at the top of the module.

The recorded value is the gateway's own spelling: `model_meta["provider"]` is
`"Nvidia"`. Normalising the field would destroy the only record that the
gateway capitalises its own vendor name.

## The fix

`_route_value_matches(field, returned, frozen)` is the one comparison, and both
halves call it. The classification is a total, disjoint partition of
`_ROUTE_FIELDS`, asserted by a test:

- `_CASELESS_ROUTE_FIELDS = ("provider", "tier")` — words
- `_EXACT_ROUTE_FIELDS = ("requested_model", "resolved_model")` — lookup keys
- `endpoint` — a URL identity, folded by `_endpoints_equal`, not a comparison

A field added to `_ROUTE_FIELDS` without being classified returns `False` from
the predicate and cannot silently inherit a verdict.

## The whole class, not the instance

`_response_meta` compares four fields. Checked each:

| field | catalog half | response half | same predicate now |
|---|---|---|---|
| `resolved_model` | exact (`:352` `exact_ids`) | exact | yes |
| `provider` | folded (`:341`) | **was** exact | yes |
| `tier` | folded, via `_catalog_free_signal` (`:397`) | **was** exact | yes |
| `endpoint` | not checked | `_endpoints_equal` | unchanged, by design |
| `requested_model` | pre-dispatch, exact (`:789`) | not in the response | n/a |

**`tier` was the same bug and is fixed with it.** The live gateway returns
`"free"` lowercase today, so the defect was latent rather than firing; a
gateway that returned `"Free"` would have been refused identically. Proven by
mutation: with `tier` excluded from the folded set,
`test_tier_is_folded_by_the_both_halves_too` fails with
`RESPONSE_METADATA`, and passes with the fix.

**`endpoint` is the third shape, not a third bug.** `_response_meta` treats an
absent `endpoint` in the body as valid (`"endpoint" not in body`), and the
catalog never checks one. That is a deliberate asymmetry with a reason: the
frozen contract's endpoint is checked against the configured endpoint before
the send (`:783`), and a body that echoes one must echo it correctly. It is
also why the returned `127.0.0.1:4000` is admitted against a frozen
`localhost:4000` — the loopback aliases fold, and always did.

No other field is optional on the way in and mandatory on the way out.

## A fourth site, outside the owned paths

`experiments/ad01/learner_revision.py:341` `_attested_route` capitalises the
first letter of the contract's own `provider` before dispatching, specifically
so that `==` would pass. It is a workaround for this defect, it is a
fourth predicate disagreeing with the other three, and it is now dead weight:
with the fix, a lower-case contract is admitted and the mutation is
unnecessary.

It is also load-bearing for a committed record. `reports/evidence/inv_r1_e4/run/campaign.json`
carries `provider_fold` on all six dispatches, and **all six dispatched under
`provider: "Nvidia"`** — a contract spelled the gateway's way, not the frozen
one. Those six succeeded because of the mutation.

Not edited: outside owned paths. It should be retired, and the campaign record
left as it is.

## Does this invalidate a committed artifact?

**No committed artifact becomes invalid. One becomes stale, and the reports
that repeat an old claim are now wrong in the direction of severity.**

Checked directly: `grep -rn "response_metadata" reports/` returns nothing. No
committed evidence records a `RESPONSE_METADATA` refusal, so no result was
computed from one.

What is affected:

- `reports/evidence/inv_r1_u2_menu/RESULT.md:159-160` — "Defect 2 alone blocks
  every live send on this route, which means the recorded M3 result of 330 of
  360 calls unspent has a second cause beside the tie." **The first clause is
  now false**; the send is admitted. The second clause stands: the M3 unspent
  figure still has the tie as a cause, and no evidence shows the route was
  what spent or withheld the other 30. The u2 dispatch itself was recorded
  `unresolved` with no receipt, so nothing in it is refuted — it is simply no
  longer evidence of a block.
- `TASKS.md:54` and `reports/STAGE-09-HANDOVER.md:248` — both record C16 as
  "the gateway never sends `provider`", which was wrong when written and is
  now contradicted by measurement in two directions. `TASKS.md` explicitly
  parked the decision as a human call "because it changes what prior runs'
  validity means"; **it does not**, and that is the answer to the question it
  was waiting on.
- `reports/evidence/inv_r1_e4/run/campaign.json` — the six dispatches stand.
  They were sent under a mutated contract, and the mutation is recorded beside
  each one, so the record is self-describing. It is a valid record of a run
  that happened; it is not evidence that a lower-case contract works, because
  it never tested one.

Nothing under `reports/evidence/` was modified.

## End to end

One live send through the real adapter, the same one the study path builds,
against `127.0.0.1:4000` with the route frozen as `SETTLEMENT_EXPECTED_ROUTE`
holds it:

```
admitted:   True
COMPLETED
  text:    'OK'
  usage:   in=23 out=16
  provider returned by gateway: 'Nvidia'
  model:                       'nvidia/nemotron-3-ultra-550b-a55b:free'
  tier:                        'free'
  route_error present:         False
```

**HTTP 200, admitted, not refused.** The same call with the pre-fix comparison
restored in place returns `GatewayRouteError.RESPONSE_METADATA` with
`response_received: True` and `response_status: 200` — the tokens spent, the
reply discarded. The fix is causal, not incidental.

## Tests

`tests/test_gateway_provider_field.py`, 15 passed. The 103 tests in
`test_gateway_boundary.py`, `test_route_refusal_fidelity.py` and
`test_output_evidence.py` pass unchanged, so the refusal behaviour for a
genuinely different provider, an absent provider and a paid tier is intact.

`test_gateway_usage_unknown.py` has 4 failures, all about charge scale rather
than route. **Pre-existing**: reproduced at `HEAD~1` with this lane's changes
reverted, same 4, same assertions. Not this lane's to fix.

## The lane's own correction

The last test in the spec file asserted that `resolved_model` was the *only*
exact field, so `requested_model` had to fold. That was the killed lane's
hypothesis, never measured. Measurement says model ids are case-sensitive, so
the test is rewritten to assert the classification is total and disjoint
(`_ROUTE_FIELDS == caseless | exact | {"endpoint"}`) instead of hardcoding one
special case. A sixth field now cannot be added without being classified.
