"""One comparison per route field, shared by the catalog and the response half.

Measured against the live gateway on 2026-09-28: `POST /v1/chat/completions`
returns `provider: "Nvidia"` for the frozen route whose contract spells the
same vendor `"nvidia"`. The catalog half of the route check
(`reconcile_model_route`) folded case and accepted it; the response half
(`_response_meta`) compared with `==` and refused the same value as
`response_metadata`, after the tokens were spent. One field, two predicates.

Both halves now call `_route_value_matches`, so the two verdicts cannot come
apart. The two remaining classification questions were measured, not assumed:

- `provider` is a **routing field**, and settlement refuses a response that
  does not name the frozen vendor. Measured: `provider` reads `Nvidia` for the
  bare id, for `openrouter/nvidia/...` and for `kilo/nvidia/...` alike, so it
  names the vendor. The catalog's `owned_by` reads `Openrouter` and `Kilo API`
  and names the aggregator, so it is a different field and is not a fallback.
- `requested_model` and `resolved_model` are **not** folded. Measured: the
  gateway answered `NVIDIA/nemotron-3-ultra-550b-a55b:free` with HTTP 503
  `auth_not_found` while `nvidia/...` returned 200. A label is a word; an id is
  a key the catalog has to answer for.

The response bodies below are the shapes the live gateway returned, kept
verbatim so the fixtures cannot drift back toward what the code assumed.
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
from settlement.gateway_http import HttpGatewayAdapter

ENDPOINT = "http://127.0.0.1:4000/v1"

# `SETTLEMENT_EXPECTED_ROUTE` as frozen for the live study.
FROZEN_ROUTE = {
    "endpoint": "http://localhost:4000/v1",
    "requested_model": "openrouter/nvidia/nemotron-3-ultra-550b-a55b:free",
    "resolved_model": "nvidia/nemotron-3-ultra-550b-a55b:free",
    "provider": "nvidia",
    "tier": "free",
}

# Field-for-field what the live gateway returned, provider capitalised.
LIVE_RESPONSE_BODY = {
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
    "tier": "free",
    "endpoint": "http://127.0.0.1:4000/v1",
}

# 128 entries, all `owned_by`, none carrying `provider` or `tier`.
LIVE_CATALOG_BODY = {
    "object": "list",
    "data": [
        {"id": FROZEN_ROUTE["resolved_model"], "object": "model",
         "created": 1790432313, "owned_by": "Openrouter"},
        {"id": FROZEN_ROUTE["requested_model"], "object": "model",
         "created": 1790432313, "owned_by": "Openrouter"},
    ],
}


def _request() -> ModelRequest:
    return ModelRequest(
        model=FROZEN_ROUTE["requested_model"],
        messages=({"role": "user", "content": "Reply with the single word: OK"},),
        max_output_tokens=16,
        deadline_ms=10_000,
        operation_id="op-c16-provider-case",
    )


def _adapter(body: dict, expected_route: dict = FROZEN_ROUTE
             ) -> HttpGatewayAdapter:
    def handler(request: httpx.Request) -> httpx.Response:
        raw = json.dumps(body).encode()
        return httpx.Response(200, stream=httpx.ByteStream(raw))

    return HttpGatewayAdapter(
        endpoint=ENDPOINT,
        api_key="test-key",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        expected_route=expected_route,
    )


def test_live_response_admits_a_capitalised_provider_for_a_lower_case_contract():
    result = _adapter(LIVE_RESPONSE_BODY).infer(_request())

    assert isinstance(result, ModelResponse)
    assert result.text == "OK"
    assert result.usage.input_tokens == 23
    assert result.usage.output_tokens == 16
    assert "route_error" not in result.model_meta
    assert result.model_meta["provider"] == "Nvidia"


def test_the_returned_provider_is_recorded_as_the_gateway_spelled_it():
    result = _adapter(LIVE_RESPONSE_BODY).infer(_request())

    assert result.model_meta["provider"] == "Nvidia"
    assert result.model_meta["model"] == FROZEN_ROUTE["resolved_model"]
    assert result.model_meta["tier"] == "free"


def test_a_different_provider_is_still_refused_after_tokens_are_spent():
    body = {**LIVE_RESPONSE_BODY, "provider": "Openrouter"}
    result = _adapter(body).infer(_request())

    assert isinstance(result, GatewayError)
    assert result.kind == GatewayErrorKind.PROTOCOL
    assert result.retryable is False
    assert result.route_error == GatewayRouteError.RESPONSE_METADATA
    assert result.response_received is True
    assert result.usage.input_tokens == 23


def test_a_absent_provider_is_still_refused_rather_than_assumed():
    body = dict(LIVE_RESPONSE_BODY)
    del body["provider"]
    result = _adapter(body).infer(_request())

    assert isinstance(result, GatewayError)
    assert result.route_error == GatewayRouteError.RESPONSE_METADATA


@pytest.mark.parametrize("frozen", ["nvidia", "NVIDIA", "NvIdIa"])
def test_every_capitalisation_of_the_frozen_provider_is_admitted(frozen: str):
    expected = {**FROZEN_ROUTE, "provider": frozen}
    result = _adapter(LIVE_RESPONSE_BODY, expected).infer(_request())

    assert isinstance(result, ModelResponse), getattr(result, "message", "")


def test_the_catalog_half_and_the_response_half_agree_about_the_live_route():
    from settlement.gateway_http import validate_model_route

    assert validate_model_route(LIVE_CATALOG_BODY, FROZEN_ROUTE) == FROZEN_ROUTE
    assert isinstance(_adapter(LIVE_RESPONSE_BODY).infer(_request()), ModelResponse)


def test_tier_is_folded_by_the_both_halves_too():
    body = {**LIVE_RESPONSE_BODY, "tier": "Free"}
    result = _adapter(body).infer(_request())

    assert isinstance(result, ModelResponse), getattr(result, "message", "")

    from settlement.gateway_http import reconcile_model_route

    catalog = {"data": [{**entry, "tier": "Free"}
                        for entry in LIVE_CATALOG_BODY["data"]]}
    catalog["data"][0]["pricing"] = {"prompt": "0", "completion": "0"}
    catalog["data"][1]["pricing"] = {"prompt": "0", "completion": "0"}
    assert reconcile_model_route(catalog, FROZEN_ROUTE)["result"]["verdict"] \
        == "accepted"


def test_a_paid_response_tier_is_refused():
    body = {**LIVE_RESPONSE_BODY, "tier": "paid"}
    result = _adapter(body).infer(_request())

    assert isinstance(result, GatewayError)
    assert result.route_error == GatewayRouteError.RESPONSE_METADATA


def test_every_case_insensitive_field_is_a_field_the_route_contract_declares():
    from settlement.gateway_http import (
        _CASE_INSENSITIVE_ROUTE_FIELDS,
        _ROUTE_FIELDS,
    )

    assert set(_CASE_INSENSITIVE_ROUTE_FIELDS) <= set(_ROUTE_FIELDS)
    assert "provider" in _CASE_INSENSITIVE_ROUTE_FIELDS
    assert "tier" in _CASE_INSENSITIVE_ROUTE_FIELDS


def test_the_two_halves_cannot_diverge_again():
    """A field added to the route contract is judged by one predicate.

    Walk both halves over every field of the contract and demand the same
    verdict. A future field that is enforced on the response and skipped in
    the catalog, or folded in one half and not the other, fails here rather
    than on a live send.
    """
    from settlement.gateway_http import (
        _CASELESS_ROUTE_FIELDS,
        _EXACT_ROUTE_FIELDS,
        _ROUTE_FIELDS,
        _route_value_matches,
    )

    classified = set(_CASELESS_ROUTE_FIELDS) | set(_EXACT_ROUTE_FIELDS)
    assert set(_ROUTE_FIELDS) == classified | {"endpoint"}
    assert not set(_CASELESS_ROUTE_FIELDS) & set(_EXACT_ROUTE_FIELDS)

    for field in _ROUTE_FIELDS:
        if field == "endpoint":
            continue
        for frozen, returned in (("vendor", "Vendor"), ("vendor", "vendor"),
                                 ("vendor", "other"), ("free", "paid")):
            assert _route_value_matches(field, returned, frozen) is (
                returned.lower() == frozen.lower() if field in _CASELESS_ROUTE_FIELDS
                else returned == frozen)


def test_a_model_id_is_not_folded_because_the_gateway_does_not_honour_the_fold():
    """A label is a word; an id is a key the catalog has to answer for.

    Measured live on 2026-09-29: `nvidia/nemotron-3-ultra-550b-a55b:free` was
    HTTP 200 and `NVIDIA/nemotron-3-ultra-550b-a55b:free` was HTTP 503
    `auth_not_found` in the same minute. Folding an id would admit a key the
    catalog cannot answer for, so ids stay exact and labels do not.
    """
    from settlement.gateway_http import _route_value_matches

    assert _route_value_matches("requested_model", "NVIDIA/nemotron:free",
                                "nvidia/nemotron:free") is False
    assert _route_value_matches("resolved_model", "Nvidia/nemotron:free",
                                "nvidia/nemotron:free") is False
    assert _route_value_matches("resolved_model", "nvidia/nemotron:free",
                                "nvidia/nemotron:free") is True


def test_provider_names_the_vendor_and_not_the_aggregator_the_catalog_names():
    """What the field means, and why the catalog's `owned_by` is not it.

    `owned_by` for the frozen route is `Openrouter`; the completion's
    `provider` is `Nvidia` for the same model, and stays `Nvidia` when the id
    is spelled `openrouter/nvidia/...` or `kilo/nvidia/...`. The two fields name
    different things, so mapping one onto the other would refuse a correct
    response, and the field is a routing field precisely because it is the one
    that survives the change of aggregator.
    """
    assert FROZEN_ROUTE["provider"] == "nvidia"
    assert LIVE_CATALOG_BODY["data"][0]["owned_by"] == "Openrouter"
    assert LIVE_RESPONSE_BODY["provider"] == "Nvidia"


def test_an_absent_provider_is_refused_rather_than_inferred_from_the_id():
    """The absent field is the case this defect hid, so it is pinned here.

    Before the fix `_returned_route` produced `None` and `None != "nvidia"`
    refused by accident. If the comparison ever starts deriving a provider from
    the model id, this refuses -- which is the point: a vendor the provider did
    not name is unverified, and settlement will not vouch for it.
    """
    from settlement.gateway_http import _returned_route

    body = dict(LIVE_RESPONSE_BODY)
    del body["provider"]
    assert _returned_route(body)["provider"] is None

    result = _adapter(body).infer(_request())

    assert isinstance(result, GatewayError)
    assert result.route_error == GatewayRouteError.RESPONSE_METADATA
