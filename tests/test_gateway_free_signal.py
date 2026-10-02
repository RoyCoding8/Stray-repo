"""One free signal, derived once, read by both halves of the contract.

`gateway_http.py` derives the free signal in two places. The catalog half
reads it off a `:free` model id; the response half reads only a `tier` field
or a `pricing` block. The live body carries neither, so the catalog half
answered `free`, the response half answered `None`, and a correct free
response was refused as `response_metadata` after its tokens were spent.
Every live construction died on that refusal.

The route table at the top of the module already repaired this shape of
defect once, for `provider`: one half folded case and the other did not. It
unified the *comparison*. It did not unify the *derivation*, and that is the
half that is still split. This file pins the derivation as one function so a
future field cannot be judged one way in the catalog and the other way in
the response, and it pins the refusals that must survive the repair, because
a check that stops refusing anything would also pass.
"""

from __future__ import annotations

import json

import httpx
import pytest

from settlement.gateway import (
    GatewayError,
    GatewayErrorKind,
    GatewayRouteError,
    ModelRequest,
    ModelResponse,
)
from settlement.gateway_http import FreeSignal, HttpGatewayAdapter

# `SETTLEMENT_EXPECTED_ROUTE` as frozen for the live study.
FROZEN_ROUTE = {
    "endpoint": "http://127.0.0.1:4000/v1",
    "requested_model": "nvidia/nemotron-3-ultra-550b-a55b:free",
    "resolved_model": "nvidia/nemotron-3-ultra-550b-a55b:free",
    "provider": "nvidia",
    "tier": "free",
}

# Field for field what the live gateway returned, measured 2026-09-29, and
# the whole of the defect: `model` and `provider` are present, `service_tier`
# is present and null, `usage.cost` is present and zero, and there is no
# `tier` key and no `pricing` key anywhere in the body. The only free
# statement it makes is the `:free` model id.
LIVE_BODY = {
    "id": "gen-1790637999-RyWZLohSuDovcrYeLWOp",
    "object": "chat.completion",
    "created": 1790637999,
    "model": "nvidia/nemotron-3-ultra-550b-a55b:free",
    "provider": "Nvidia",
    "system_fingerprint": None,
    "service_tier": None,
    "choices": [{
        "index": 0,
        "finish_reason": "length",
        "native_finish_reason": "length",
        "message": {"role": "assistant", "content": "OK", "reasoning": None},
    }],
    "usage": {
        "prompt_tokens": 23,
        "completion_tokens": 16,
        "total_tokens": 39,
        "cost": 0,
        "is_byok": False,
    },
}


def _request() -> ModelRequest:
    return ModelRequest(
        model=FROZEN_ROUTE["requested_model"],
        messages=({"role": "user", "content": "Reply with the single word: OK"},),
        max_output_tokens=16,
        deadline_ms=10_000,
        operation_id="op-w1-free-signal",
    )


def _adapter(body: dict, expected_route: dict | None = FROZEN_ROUTE
             ) -> HttpGatewayAdapter:
    def handler(request: httpx.Request) -> httpx.Response:
        raw = json.dumps(body).encode()
        return httpx.Response(200, stream=httpx.ByteStream(raw), request=request)

    return HttpGatewayAdapter(
        endpoint=FROZEN_ROUTE["endpoint"],
        api_key="test-key",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        expected_route=expected_route,
    )


def test_the_live_body_reaches_a_model_instead_of_being_refused():
    """The unblock, stated as the caller sees it.

    Before the repair this exact body came back as
    `route_error = RESPONSE_METADATA` with the tokens already spent, and no
    live construction could get past it. The provider capitalises `provider`
    against a frozen `nvidia`, which the route table already admits; the tier
    is what refused.
    """
    result = _adapter(LIVE_BODY).infer(_request())

    assert isinstance(result, ModelResponse), getattr(result, "message", "")
    assert result.text == "OK"
    assert result.usage.input_tokens == 23
    assert result.usage.output_tokens == 16
    assert "route_error" not in result.model_meta
    assert result.model_meta["model"] == FROZEN_ROUTE["resolved_model"]
    assert result.model_meta["provider"] == "Nvidia"
    assert result.model_meta["tier"] == "free"


def test_both_halves_read_the_same_derivation_of_the_live_body():
    """One body, one answer. The catalog half and the response half agree.

    This is the invariant the defect broke. The catalog is judged by
    `_free_signal` and the response is judged by `_returned_route`, and
    `_returned_route` is a reader of the same call, so the two can no longer
    come apart on `tier` no matter which fields the body happens to carry.
    """
    from settlement.gateway_http import _free_signal, _returned_route

    catalog_signal = _free_signal(LIVE_BODY, LIVE_BODY["model"])
    assert catalog_signal.refusal is None
    assert _returned_route(LIVE_BODY)["tier"] == catalog_signal.tier
    assert catalog_signal.tier == "free"


def test_the_second_derivation_is_deleted_rather_than_left_beside_the_first():
    """Two functions that both answer "is this free" is the defect itself.

    Keeping either old name alive would let a caller reach the narrower one,
    which is how a third way to ask the question got written in the first
    place. The name must be gone, not merely unreferenced.
    """
    from settlement import gateway_http

    assert not hasattr(gateway_http, "_free_tier")
    assert not hasattr(gateway_http, "_catalog_free_signal")


def test_a_stated_paid_tier_refuses_a_free_named_model():
    """The negative, in the shape that matters most: the name says free.

    If the `:free` id suffix alone could carry a route, then a document that
    states `paid` would be waved through on the strength of its own name. The
    stated label decides, and it decides against.
    """
    body = {**LIVE_BODY, "tier": "paid"}
    result = _adapter(body).infer(_request())

    assert isinstance(result, GatewayError)
    assert result.kind == GatewayErrorKind.PROTOCOL
    assert result.retryable is False
    assert result.route_error == GatewayRouteError.RESPONSE_METADATA
    assert result.response_received is True


def test_a_paid_price_refuses_a_free_named_model_in_the_catalog():
    """The same negative on the catalog side, with a different price channel.

    The catalog states price rather than tier, and a nonzero price refuses
    the route whatever the entry is called. The catalog refusal is raised,
    so the caller reads the reason rather than a status.
    """
    from settlement.gateway_http import validate_model_route

    body = {"data": [
        {"id": FROZEN_ROUTE["requested_model"],
         "owned_by": "Openrouter",
         "pricing": {"prompt": "0.000001", "completion": "0"}},
        {"id": FROZEN_ROUTE["resolved_model"],
         "owned_by": "Openrouter",
         "pricing": {"prompt": "0.000001", "completion": "0"}},
    ]}
    with pytest.raises(ValueError, match="paid pricing"):
        validate_model_route(body, FROZEN_ROUTE)


def test_a_body_that_says_nothing_free_is_refused_not_assumed():
    """Silence is not consent. A route that cannot be shown free is not free.

    Same provider, same shape, no `tier`, no `pricing`, and a model id with
    no `:free` suffix. Nothing in it is a free statement, so the derivation
    has to refuse rather than fall through to an accept.
    """
    body = {**LIVE_BODY, "model": "nvidia/nemotron-3-ultra-550b-a55b"}
    result = _adapter(body).infer(_request())

    assert isinstance(result, GatewayError)
    assert result.route_error == GatewayRouteError.RESPONSE_METADATA


def test_a_malformed_price_is_not_a_free_price():
    """A price that will not parse is not a price of zero.

    `float()` on a non-numeric string raises rather than returning 0, and a
    boolean is not a number. Both are refusals, so a catalog cannot smuggle
    a paid model past the check by writing `true`.
    """
    from settlement.gateway_http import _free_signal

    assert _free_signal({"pricing": {"prompt": "free", "completion": "0"}},
                        "vendor/paid").refusal == "pricing is malformed"
    assert _free_signal({"pricing": {"prompt": True, "completion": 0}},
                        "vendor/paid").refusal == "pricing is malformed"
    assert _free_signal({"pricing": {"prompt": 0, "completion": 0.0}},
                        "vendor/paid") == FreeSignal("free")
    assert _free_signal({"pricing": {"prompt": 0, "completion": 0.01}},
                        "vendor/free:free").refusal == "explicit paid pricing"


def test_a_free_label_beside_a_paid_price_is_a_contradiction():
    """Two statements that disagree, and neither wins by default.

    This is the case the old `tier without pricing` rule was reaching for
    by refusing every tier it had no price to check. Refusing the
    contradiction is the honest reading of it, and it leaves a lone
    `tier: "free"` admitted, because a label and a name are the same kind
    of claim by the same writer.
    """
    from settlement.gateway_http import _free_signal

    assert _free_signal({"tier": "free",
                         "pricing": {"prompt": "0.5", "completion": "0"}},
                        "vendor/free:free").refusal == "explicit paid pricing"


def test_zero_cost_is_not_one_of_the_signals():
    """Pin the trust decision about `usage.cost`, on both sides.

    `usage.cost == 0` is a real statement the provider makes about the call
    it just served, and it is on every free response. It is deliberately not
    a channel, for a reason the refusals below state rather than assert: a
    cost figure describes a call that has already been paid for, so reading
    it cannot refuse before the spend, and no catalog entry carries one, so
    a route admitted by it would pass live and fail preflight. The preflight
    is the pre-token gate, and it reads the catalog.
    """
    from settlement.gateway_http import _free_signal

    # A paid label outranks a zero bill. The label is a statement about the
    # route; the cost is a statement about one call on it.
    paid_but_zero = {**LIVE_BODY, "tier": "paid", "model": "nvidia/other"}
    assert _free_signal(paid_but_zero, "nvidia/other").refusal == \
        "explicit paid tier"

    # And a zero bill is not itself a free route. The number is the
    # provider's accounting for the call just served, not the route
    # contract, so on its own it establishes nothing and is refused.
    cost_only = {**LIVE_BODY, "model": "nvidia/other"}
    assert cost_only["usage"]["cost"] == 0
    assert _free_signal(cost_only, "nvidia/other").refusal == "no signal"

    # The same document with the free name is admitted, which is the whole
    # unblock, and the name is doing the work rather than the zero.
    named = {**LIVE_BODY, "model": FROZEN_ROUTE["resolved_model"]}
    assert named["usage"]["cost"] == 0
    assert _free_signal(named, named["model"]) == FreeSignal("free")


def test_a_stated_free_label_is_folded_the_same_way_in_both_halves():
    """Case folding stays in the route table, and still reaches both halves.

    The derivation reports what the document said. Whether that agrees with
    the frozen contract is the route table's job, and it is one table, so a
    label the gateway spells `Free` is admitted the same way on the catalog
    side and the response side.
    """
    from settlement.gateway_http import _returned_route, validate_model_route

    body = {**LIVE_BODY, "tier": "Free"}
    result = _adapter(body).infer(_request())
    assert isinstance(result, ModelResponse), getattr(result, "message", "")

    # A free label is a free label, so the derivation answers `free` whatever
    # case it was written in. The spelling is preserved for `provider`, which
    # names a party; a tier names a class, and the class is the claim.
    assert _returned_route(body)["tier"] == "free"

    catalog = {"data": [
        {"id": FROZEN_ROUTE["requested_model"], "owned_by": "Openrouter",
         "tier": "Free", "pricing": {"prompt": "0", "completion": "0"}},
    ]}
    assert validate_model_route(catalog, FROZEN_ROUTE) == FROZEN_ROUTE
