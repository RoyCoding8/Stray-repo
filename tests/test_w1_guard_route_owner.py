"""The counting guard must judge a route the way the adapter judges it.

`HttpGatewayAdapter._response_meta` accepts the live body: the gateway
answers `provider: "Nvidia"` against a route frozen as `nvidia`, and
`_route_value_matches` folds case for `provider` the way the catalog half
does. `LiveGuard._route_failure` compared the same two values with raw dict
equality, so it refused what the adapter had already admitted. The E1
campaign then recorded zero constructions across eight attempts with the
tokens already spent, and filed every one of them as a route refusal, which
reads as a claim about the model and is not one.

The route rule already has one owner for a single field. This file pins the
second half of that claim: a whole route, judged in one call, by the owner,
so no caller can judge the same route a different way.

Every assertion is made at `_preflight_dispatch`, the function that returns
the taxonomy value the campaign records. That is the decision this defect
moved, and it covers both ways a route is refused: the adapter returning an
error the guard propagates, and the guard raising on its own check. A test
that only asserted one of those would pass on half the defect.

The refusals are asserted as loudly as the admission. A repair that made
the guard accept everything would pass the first case and mean nothing, so
each way a route can genuinely be wrong is pinned to `route-refusal` here.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from experiments.ad01 import live_construct as live
from settlement.gateway import ModelRequest
from settlement.gateway_http import (
    HttpGatewayAdapter, _returned_route, route_matches)

ROUTE = live.OUTPUT_ROUTE

# Four legal specs that all predict zero. It parses and it is wrong, which
# makes the taxonomy value after the route check a fixed literal: reaching
# `poor-task-result` proves the route was admitted and the content was
# carried to the parser, where a route refusal would have stopped the run.
ZERO_PROGRAM = json.dumps(
    {"specs": [{"const": 0, "mask": 0, "pair": None}] * 4})

#: The same id with the `:free` suffix removed. The body states no tier and
#: quotes no price, so the suffix is the only free statement it makes, and
#: without it the body has established nothing.
PAID_MODEL = ROUTE["resolved_model"].removesuffix(":free")

# Field for field what the live gateway returned, measured 2026-09-29:
# `provider` capitalised, `service_tier` present and null, `usage.cost`
# present and zero, no `tier` key and no `pricing` key anywhere. The only
# free statement the body makes is the `:free` model id.
LIVE_BODY = {
    "id": "gen-1790637999-RyWZLohSuDovcrYeLWOp",
    "object": "chat.completion",
    "created": 1790637999,
    "model": ROUTE["resolved_model"],
    "provider": "Nvidia",
    "system_fingerprint": None,
    "service_tier": None,
    "choices": [{
        "index": 0,
        "finish_reason": "stop",
        "native_finish_reason": "stop",
        "message": {"role": "assistant", "content": ZERO_PROGRAM,
                    "reasoning": None},
    }],
    "usage": {
        "prompt_tokens": 23,
        "completion_tokens": 16,
        "total_tokens": 39,
        "cost": 0,
        "is_byok": False,
    },
}

# The router is reached at its loopback address while the route is frozen
# with the `localhost` alias, so the guard is asked the endpoint question
# it will actually be asked and the endpoint join is exercised.
ROUTED_ENDPOINT = "http://127.0.0.1:4000/v1"


def _adapter(body: dict, endpoint: str = ROUTED_ENDPOINT) -> HttpGatewayAdapter:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, stream=httpx.ByteStream(json.dumps(body).encode()),
            request=request)

    return HttpGatewayAdapter(
        endpoint=endpoint, api_key="test-key", api="chat",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        expected_route=dict(ROUTE))


def _guard(gateway) -> live.LiveGuard:
    return live.LiveGuard(
        gateway, pinned_model=ROUTE["requested_model"], ceiling=1,
        automatic_retries=0, expected_route=dict(ROUTE))


def _dispatch(body: dict, endpoint: str = ROUTED_ENDPOINT) -> dict:
    """One preflight attempt through the shipped guard and parser."""
    return live._preflight_dispatch(_guard(_adapter(body, endpoint)),
                                    arm="P1", attempt=1)


def test_the_live_body_reaches_a_construction_through_the_guard():
    """The unblock, stated as the campaign saw it.

    Eight attempts, zero constructions, `route-refusal` on each, tokens
    spent. The response was good and the guard threw it away. Driven here
    through the shipped adapter, guard and parser, the same body has to
    get past the route and be scored.
    """
    attempt = _dispatch(LIVE_BODY)

    assert attempt["outcome"] == "poor-task-result", attempt["reason"]
    assert attempt["score"]["overall"] == 0.0625
    assert attempt["dispatch"]["route_error"] is None
    assert attempt["dispatch"]["provider"] == "Nvidia"
    assert attempt["dispatch"]["returned_model"] == ROUTE["resolved_model"]


def test_the_guard_reports_no_route_error_on_the_live_body():
    """The same fact read off the response rather than the taxonomy.

    `route-refusal` is reached two ways, and the one this defect tripped is
    the guard refusing a response the adapter had already admitted. So the
    response itself is asserted clean, which is the shape a caller sees.
    """
    response = _guard(_adapter(LIVE_BODY)).infer(ModelRequest(
        model=ROUTE["requested_model"],
        messages=({"role": "user", "content": "one JSON object"},),
        max_output_tokens=64, deadline_ms=10_000,
        operation_id="op-w1-guard-route"))

    assert not isinstance(response, Exception), response
    assert response.text == ZERO_PROGRAM
    assert "route_error" not in response.model_meta


@pytest.mark.parametrize("label, body, endpoint", [
    ("a different vendor", {**LIVE_BODY, "provider": "Anthropic"},
     ROUTED_ENDPOINT),
    ("no vendor stated", {k: v for k, v in LIVE_BODY.items()
                          if k != "provider"}, ROUTED_ENDPOINT),
    ("a different model", {**LIVE_BODY, "model": "other/resolved:free"},
     ROUTED_ENDPOINT),
    ("a paid model", {**LIVE_BODY, "model": PAID_MODEL}, ROUTED_ENDPOINT),
    ("a stated paid tier", {**LIVE_BODY, "tier": "paid"}, ROUTED_ENDPOINT),
    ("a different endpoint", LIVE_BODY, "http://127.0.0.1:4001/v1"),
])
def test_a_wrong_route_still_refuses(label, body, endpoint):
    """The fold is for spelling, not for disagreement.

    `Nvidia` and `nvidia` are one vendor written twice. Every case here is
    a different vendor, a missing vendor, a different model, a paid model,
    a stated paid tier, or a different host. If any of them is admitted,
    the repair weakened the route rather than unifying it.
    """
    attempt = _dispatch(body, endpoint)

    assert attempt["outcome"] == "route-refusal", (
        f"{label} was reported as {attempt['outcome']!r}: {attempt['reason']}")


def test_the_guard_and_the_adapter_cannot_disagree_about_one_route():
    """The claim the repair makes, asserted over bodies rather than prose.

    `route_matches` is the one comparison of a whole route, and both the
    adapter and the guard reach it with the fields a response carries. So
    the two verdicts have to agree for every body: no body may be admitted
    by one half and refused by the other. The cases span the three kinds of
    route field, a caseless label spelled two ways, an exact id, and a field
    the body never states.
    """
    cases = {
        "live body as returned": LIVE_BODY,
        "vendor folded to the frozen spelling": {
            **LIVE_BODY, "provider": ROUTE["provider"]},
        "a different vendor": {**LIVE_BODY, "provider": "Anthropic"},
        "no vendor stated": {k: v for k, v in LIVE_BODY.items()
                             if k != "provider"},
        "a different model": {**LIVE_BODY, "model": "other/resolved:free"},
        "a paid model": {**LIVE_BODY, "model": PAID_MODEL},
        "a stated paid tier": {**LIVE_BODY, "tier": "paid"},
    }
    for label, body in cases.items():
        attempt = _dispatch(body)
        # Read the body the way the adapter does, then judge it with the
        # owner. The campaign's verdict has to be the negation of that.
        returned = {**_returned_route(body), "endpoint": ROUTED_ENDPOINT}
        owner_admits = route_matches(returned, dict(ROUTE))
        campaign_refused = attempt["outcome"] == "route-refusal"
        assert owner_admits != campaign_refused, (
            f"{label}: the owner admits it as {owner_admits} and the campaign "
            f"reported {attempt['outcome']!r}")


def test_the_returned_route_is_read_once_and_judged_by_its_owner():
    """`route_matches` is the answer, and it refuses what it cannot read.

    Called the way the guard calls it: a whole returned route in response
    keys, a whole frozen route in route keys. A field the returned side
    omits or states as a non-string is a refusal rather than a match.
    """
    returned = {"model": ROUTE["resolved_model"], "provider": "Nvidia",
                "tier": "free", "endpoint": ROUTED_ENDPOINT}
    assert route_matches(returned, dict(ROUTE)) is True
    assert route_matches({**returned, "provider": "nvidia"}, dict(ROUTE)) is True

    for field, wrong in (("provider", "Anthropic"), ("tier", "paid"),
                         ("model", "other/resolved:free"),
                         ("endpoint", "http://127.0.0.1:4001/v1")):
        assert route_matches({**returned, field: wrong}, dict(ROUTE)) is False, (
            f"a wrong {field} was admitted")

    for field in ("model", "provider", "tier", "endpoint"):
        assert route_matches({**returned, field: None}, dict(ROUTE)) is False, (
            f"an absent {field} was admitted")


def test_a_route_field_the_guard_does_not_carry_is_refused():
    """A field the guard never reads cannot silently pass.

    The guard reads four route fields out of a dispatch record. If a fifth
    is added to the frozen route and never joined, the guard must refuse
    rather than pass a route it never compared, which is the shape of the
    defect this file repairs.
    """
    guard = _guard(_adapter(LIVE_BODY))
    entry = {"endpoint": ROUTED_ENDPOINT,
             "returned_model": ROUTE["resolved_model"], "provider": "Nvidia",
             "tier": "free", "route_error": None}

    assert guard._route_failure(entry) is None

    for missing in ("endpoint", "returned_model", "provider", "tier"):
        incomplete = {key: value for key, value in entry.items()
                      if key != missing}
        assert guard._route_failure(incomplete) == (
            "returned route metadata does not match the frozen route"), (
            f"a dispatch record with no {missing} was accepted")
