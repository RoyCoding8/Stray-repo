"""The frozen route against the two gateway surfaces, decided from the body.

`provider` is a routing field, not a note. `route_matches` refuses a
response that does not carry it, so a surface that publishes no
`provider` can never establish route identity, however correct the
answer was and however many tokens it cost.

The OpenAI Responses API publishes `id`, `object`, `status`, `model`,
`output`, `service_tier` and `usage`, and no `provider`. The local
gateway does not add one for this route either: `_attest_route` in
`modules/router.py` injects `provider` only on the pooled member path
(`_forward_pool` passes a member, `_forward_once` passes `None`), and
the frozen route is not a pool name, so a call on it is forwarded
unattested. The chat surface carries `provider: "Nvidia"` from
upstream, measured 2026-09-29 and recorded in
`reports/evidence/inv_r1_u2_menu/RESULT.md`.

So the responses surface is refused by name, before the wire. The
alternative, reading a `provider` off a body that does not carry one,
would manufacture the agreement the route check exists to demand, and
a route check that agrees with everything is not a check.

The refusal is scoped to the frozen route, not to the API: a responses
call with no route to verify is still built and still sent, which the
last test here pins.
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
    RouteContract,
)
from settlement.gateway_http import HttpGatewayAdapter

ENDPOINT = "http://localhost:4000/v1"
FROZEN = {
    "endpoint": ENDPOINT,
    "requested_model": "nvidia/nemotron-3-ultra-550b-a55b:free",
    "resolved_model": "nvidia/nemotron-3-ultra-550b-a55b:free",
    "provider": "nvidia",
    "tier": "free",
}

# Every field the responses API publishes on the frozen route, measured
# against the OpenAI Responses schema and confirmed to carry no
# `provider`: `service_tier` null, `usage.cost` zero, no `tier` key and
# no `pricing` key anywhere. The `:free` model id is the only free
# statement on it, which is what `_free_signal` already reads.
RESPONSES_BODY = {
    "id": "resp_w1",
    "object": "response",
    "created_at": 1759000000,
    "status": "completed",
    "model": "nvidia/nemotron-3-ultra-550b-a55b:free",
    "output": [{
        "type": "message",
        "id": "msg_w1",
        "role": "assistant",
        "status": "completed",
        "content": [{"type": "output_text", "text": "OK", "annotations": []}],
    }],
    "service_tier": None,
    "usage": {"input_tokens": 34, "output_tokens": 72,
              "total_tokens": 106, "cost": 0},
}

# The chat body measured on the same route the same day. `provider` is
# spelled `Nvidia` against a frozen `nvidia`, which is why `provider` is
# a caseless label.
CHAT_BODY = {
    "id": "gen-x",
    "object": "chat.completion",
    "created": 1759000000,
    "model": "nvidia/nemotron-3-ultra-550b-a55b:free",
    "provider": "Nvidia",
    "service_tier": None,
    "choices": [{"index": 0, "finish_reason": "stop", "message": {
        "role": "assistant", "content": "OK"}}],
    "usage": {"prompt_tokens": 900, "completion_tokens": 48, "cost": 0},
}


def _request() -> ModelRequest:
    return ModelRequest(
        model=FROZEN["requested_model"],
        messages=({"role": "user", "content": "probe"},),
        max_output_tokens=64,
        deadline_ms=5_000,
        operation_id="w1-responses",
    )


def _dispatch(api: str, body: dict, route: dict | None = FROZEN,
              endpoint: str = ENDPOINT, route_mode: str = "free"):
    """Answer `body` to `api` over a mock socket, recording every send."""
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        raw = json.dumps(body).encode()
        return httpx.Response(200, stream=httpx.ByteStream(raw))

    adapter = HttpGatewayAdapter(
        endpoint=endpoint,
        api_key="unused",
        api=api,
        expected_route=RouteContract.from_mapping(route) if route else None,
        route_mode=route_mode,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    return adapter.infer(_request()), calls


def test_the_responses_surface_is_refused_without_spending_a_token():
    """The whole defect, in one assertion: nothing goes on the wire.

    Before the repair this call was dispatched, the body came back, the
    text was correct, and `_response_meta` refused it three seconds later
    as `response_metadata` because the surface publishes no `provider`
    to compare. A refusal that can only be discovered by sending is a
    refusal the study pays for, and it is now a refusal it does not pay
    for.
    """
    result, calls = _dispatch("responses", RESPONSES_BODY)

    assert isinstance(result, GatewayError)
    assert calls == [], (
        "the responses surface was dispatched on a route it cannot attest")
    assert result.route_error == GatewayRouteError.RESPONSE_METADATA
    assert result.response_received is False


def test_the_refusal_is_accounted_as_a_send_that_never_happened():
    """A pre-send refusal must cost nothing, or the ceiling lies.

    `broker._model_error_receipt` branches on `route_error is not None
    and not response_received`, and files that as
    `pre-send-route-refusal` with `actual_cost: 0` and `sent: False`.
    The other two branches are the expensive ones: a refusal that came
    back is billed, and one that arrived without a `route_error` is
    recorded as a send whose answer is missing, which the study carries
    as unrecoverable exposure.
    """
    from settlement.broker import _model_error_receipt

    result, _ = _dispatch("responses", RESPONSES_BODY)
    receipt, sent = _model_error_receipt("w1-offline", result)

    assert receipt.content["response_class"] == "pre-send-route-refusal"
    assert receipt.actual_cost == 0
    assert sent is False
    assert receipt.outcome == "failure"


def test_the_refusal_names_the_field_the_surface_does_not_publish():
    """A refusal a reader cannot act on is a defect wearing a refusal."""
    result, _ = _dispatch("responses", RESPONSES_BODY)
    assert "provider" in result.message
    assert "responses" in result.message


def test_the_chat_surface_carries_the_frozen_route_and_is_admitted():
    """The surface that can attest it is admitted, `Nvidia` and all.

    This is the positive half. Without it the refusal above would be
    indistinguishable from a repair that simply refuses every route.
    """
    result, calls = _dispatch("chat", CHAT_BODY)

    assert not isinstance(result, GatewayError), result.message
    assert len(calls) == 1
    assert result.text == "OK"
    assert result.model_meta["model"] == FROZEN["resolved_model"]
    assert result.model_meta["provider"] == "Nvidia"
    assert result.model_meta["tier"] == "free"
    assert "route_error" not in result.model_meta


@pytest.mark.parametrize("body,defect", [
    ({**CHAT_BODY, "provider": "Openai"}, "a vendor the route did not name"),
    ({**CHAT_BODY, "model": "openrouter/nvidia/nemotron-3-ultra-550b-a55b"},
     "a model the route did not name"),
    ({key: value for key, value in CHAT_BODY.items() if key != "provider"},
     "no provider at all"),
])
def test_a_chat_response_off_the_frozen_route_is_still_refused(body, defect):
    """The repair refuses one surface, not the route check.

    Each body is otherwise a correct answer on the right endpoint. The
    send happened and the response came back, which is exactly when a
    wrong route must refuse: silently accepting any of these would make
    the route check a formality and the campaign's constructions
    unfalsifiable.
    """
    result, calls = _dispatch("chat", body)

    assert isinstance(result, GatewayError), f"{defect} was admitted"
    assert result.route_error == GatewayRouteError.RESPONSE_METADATA
    assert len(calls) == 1, "the refusal belongs to the response, not the wire"


def test_a_route_reached_at_another_endpoint_is_refused_before_the_send():
    """The one refusal that costs nothing, and still holds."""
    result, calls = _dispatch("chat", CHAT_BODY,
                              endpoint="http://localhost:4999/v1")

    assert isinstance(result, GatewayError)
    assert calls == []
    assert result.route_error == GatewayRouteError.ENDPOINT


def test_the_refusal_is_scoped_to_the_frozen_route_not_to_the_api():
    """Responses is not banned. A response with nothing to attest is.

    A study that routes responses with no frozen route gets its call
    built and sent, because there is no route claim to fail. Refusing
    the API by name instead would have removed the surface that carries
    `reasoning_effort`, which `broker._validate_model` accepts on the
    strength of it.
    """
    result, calls = _dispatch("responses", RESPONSES_BODY, route=None,
                              route_mode="paid")

    assert not isinstance(result, GatewayError), result.message
    assert len(calls) == 1
    assert result.text == "OK"


def test_responses_remains_an_offered_api():
    """The decision is a route decision, so `APIS` still offers both.

    If the repair had deleted `responses` from `APIS`, the two tests
    above would pass while the surface the repository routes
    `reasoning_effort` to had stopped existing.
    """
    from settlement.gateway_http import APIS

    assert APIS == ("chat", "responses")
